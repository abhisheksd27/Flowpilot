"""Fail-closed subprocess execution using macOS Seatbelt or a hardened Docker container."""
import ast
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import tempfile
import uuid
from config import ROOT, Settings

ALLOWED_IMPORTS = {"pandas", "numpy", "duckdb", "requests", "json", "datetime", "math"}
DENIED_NAMES = {"eval", "exec", "compile", "open", "input", "getattr", "setattr", "delattr",
                "globals", "locals", "vars", "dir", "breakpoint", "help", "type", "object"}


class SandboxPolicyError(ValueError):
    """Code or environment cannot satisfy the execution security policy."""


def validate_code(code: str) -> None:
    """Reject disallowed imports and introspection before the OS boundary is used."""
    if len(code) > 100_000:
        raise SandboxPolicyError("Program exceeds 100 KB")
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name not in ALLOWED_IMPORTS for alias in node.names):
                raise SandboxPolicyError("Import outside the allowlist")
        if isinstance(node, ast.ImportFrom):
            if node.level or node.module not in ALLOWED_IMPORTS or any(a.name.startswith("_") for a in node.names):
                raise SandboxPolicyError("Import outside the allowlist")
        if isinstance(node, ast.Name) and (node.id.startswith("__") or node.id in DENIED_NAMES):
            raise SandboxPolicyError(f"Forbidden capability: {node.id}")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in {"eval", "query", "load", "loads", "read_pickle", "to_pickle", "system", "popen"}):
            raise SandboxPolicyError(f"Forbidden attribute: {node.attr}")


def code_fingerprint(code: str) -> str:
    """Ignore comments/formatting when comparing repairs."""
    from tools.cache import digest
    return digest(ast.dump(ast.parse(code), include_attributes=False))


def run_python(code: str, *, settings: Settings | None = None, snapshots: dict | None = None,
               plan: dict | None = None, attempt_dir: Path | None = None) -> dict:
    """Run isolated Python for at most 30 seconds; return bounded captured output."""
    settings = settings or Settings.from_env()
    settings.prepare()
    validate_code(code)
    job = (attempt_dir or Path(tempfile.mkdtemp(dir=settings.data_dir / "runs"))).resolve()
    if not job.is_relative_to(settings.data_dir.resolve()):
        raise SandboxPolicyError("Attempt directory must be inside DATA_DIR")
    job.mkdir(parents=True, exist_ok=True)
    worker = ROOT / "tools" / "_sandbox_worker.py"
    payload = {"code": code, "snapshots": snapshots or {}, "plan": plan or {}, "job": str(job)}
    backend = settings.sandbox_backend
    if backend == "auto":
        backend = "macos" if platform.system() == "Darwin" else "docker"
    environment = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(job), "TMPDIR": str(job),
                   "PYTHONDONTWRITEBYTECODE": "1", "OPENBLAS_NUM_THREADS": "1", "OMP_NUM_THREADS": "1"}
    container_name = "flowpilot-" + uuid.uuid4().hex
    if backend == "macos":
        # Read access to runtime libraries is necessary; user files and other runs
        # are not exposed. Generated code has no general network/process access.
        runtime_paths = {str(Path(sys.base_prefix).resolve()), str(Path(sys.prefix).resolve()),
                         "/System", "/usr/lib", "/usr/share", "/Library/Apple"}
        rules = "\n".join(f'(allow file-read* (subpath {json.dumps(p)}))' for p in runtime_paths)
        profile = f'''(version 1)
(deny default)
(allow process-exec (subpath {json.dumps(str(Path(sys.base_prefix).resolve()))}) (subpath {json.dumps(str(Path(sys.prefix).resolve()))}))
(allow sysctl-read mach-lookup)
(allow file-read-metadata)
(allow file-read* (literal "/"))
(allow file-read* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))
(allow file-write* (literal "/dev/null"))
(allow file-read* (literal {json.dumps(str(worker))}))
(allow file-read* file-write* (subpath {json.dumps(str(job))}))
{rules}
'''
        command = ["/usr/bin/sandbox-exec", "-p", profile, sys.executable, "-I", str(worker)]
    elif backend == "docker":
        payload["job"] = "/work"
        command = ["docker", "run", "--rm", "-i", "--name", container_name, "--network=none",
                   "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                   "--memory=768m", "--cpus=1", "--pids-limit=32", "--user", f"{os.getuid()}:{os.getgid()}",
                   "--mount", f"type=bind,src={job},dst=/work", "--workdir=/work",
                   "-e", "HOME=/work", "-e", "TMPDIR=/work", settings.sandbox_image]
        environment["HOME"] = str(Path.home())  # Docker CLI config; not passed into the container.
    else:
        raise SandboxPolicyError("Use auto, macos, or docker; there is no unsafe fallback")
    try:
        process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, cwd=job, env=environment, start_new_session=True)
        try:
            stdout, stderr = process.communicate(json.dumps(payload).encode(), timeout=settings.python_timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()
            if backend == "docker":
                subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10)
            return {"success": False, "error": "Python execution timed out", "timed_out": True, "backend": backend}
    except FileNotFoundError as error:
        raise SandboxPolicyError(f"Isolation backend unavailable: {backend}") from error
    if process.returncode != 0:
        message = stderr.decode(errors="replace")[-8000:]
        if "sandbox_apply" in message or "Cannot connect" in message or "permission denied" in message:
            raise SandboxPolicyError("Isolation backend unavailable: " + message)
        return {"success": False, "error": message or f"Sandbox process failed (exit {process.returncode})", "backend": backend}
    try:
        result = json.loads(stdout)
    except ValueError:
        return {"success": False, "error": "Sandbox returned malformed output", "backend": backend}
    result.update({"backend": backend, "db_path": str(job / "staging.duckdb")})
    return result
