"""Private worker. Only launch through the OS-isolated parent runner."""
import builtins
import contextlib
import copy
import datetime
import io
import json
import math
import os
from pathlib import Path
import resource
import sys
import traceback
import types
import duckdb
import numpy
import pandas

payload = json.load(sys.stdin)
job = Path(payload["job"]).resolve()
os.chdir(job)
resource.setrlimit(resource.RLIMIT_FSIZE, (64 * 1024 * 1024, 64 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_CPU, (25, 25))
if sys.platform != "darwin":
    resource.setrlimit(resource.RLIMIT_AS, (1536 * 1024 * 1024, 1536 * 1024 * 1024))
resource.setrlimit(resource.RLIMIT_NOFILE, (128, 128))


class LimitedOutput(io.StringIO):
    """Keep even infinite printing from exhausting the parent process memory."""
    def write(self, value):
        if self.tell() + len(value) > 32768:
            raise RuntimeError("Generated program output exceeds 32 KB")
        return super().write(value)


written = False

def call_api(source):
    """Expose only approved immutable input snapshots."""
    if source not in payload["snapshots"]:
        raise ValueError("Request is not in the approved snapshot catalog")
    return copy.deepcopy(payload["snapshots"][source])


def load_frame(frame):
    """Idempotently load the current attempt's staging table only."""
    global written
    if not isinstance(frame, pandas.DataFrame) or len(frame) > 100_000:
        raise ValueError("Expected a DataFrame with at most 100,000 rows")
    with duckdb.connect(str(job / "staging.duckdb"), config={"enable_external_access": "false", "threads": "1"}) as con:
        con.register("incoming", frame)
        con.execute("CREATE OR REPLACE TABLE staged AS SELECT * FROM incoming")
    written = True


allowed = {"pandas": pandas, "numpy": numpy, "json": json, "datetime": datetime, "math": math,
           "requests": types.SimpleNamespace(get=lambda *a, **k: (_ for _ in ()).throw(PermissionError("Use call_api snapshot broker"))),
           "duckdb": types.SimpleNamespace(connect=lambda *a, **k: (_ for _ in ()).throw(PermissionError("Use load_frame staging helper")))}

def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name not in allowed:
        raise ImportError("Import not allowed: " + name)
    return allowed[name]


safe_names = ("abs", "all", "any", "bool", "dict", "enumerate", "float", "int", "isinstance",
              "len", "list", "max", "min", "print", "range", "round", "set", "sorted", "str",
              "sum", "tuple", "zip", "Exception", "ValueError", "RuntimeError")
safe_builtins = {name: getattr(builtins, name) for name in safe_names}
safe_builtins["__import__"] = restricted_import
environment = {"__builtins__": safe_builtins, "call_api": call_api, "load_frame": load_frame,
               "plan": payload["plan"]}
out, err = LimitedOutput(), LimitedOutput()
try:
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        exec(compile(payload["code"], "<generated-pipeline>", "exec"), environment)
    if not written:
        raise ValueError("Generated code did not load a staging table")
    result = {"success": True, "stdout": out.getvalue(), "stderr": err.getvalue()}
except BaseException as error:
    result = {"success": False, "error": f"{type(error).__name__}: {error}",
              "stdout": out.getvalue(), "stderr": err.getvalue(), "traceback": traceback.format_exc()[-8000:]}
print(json.dumps(result))
