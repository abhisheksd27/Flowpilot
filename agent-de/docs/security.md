# Security and Execution Boundaries

These are implementation requirements. No sandbox implementation or successful isolation test currently exists in this project.

## Trust model

Trust host configuration and explicitly implemented tool policy. Treat user requests, API data, LLM output, and generated Python as untrusted input. Text from any of those inputs cannot expand permissions.

The main warehouse, metadata, provider credentials, and unrelated filesystem content must remain outside generated code's writable scope.

## Generated Python

Use a subprocess with a 30-second execution deadline and operating-system or container isolation. Permit runtime data access only within the assigned attempt directory under `data/`. Allow only the narrowly necessary read access to interpreter, installed libraries, and system runtime files. This runtime exception is not permission to read user files.

The environment must exclude provider credentials. Deny unrestricted network access and child-process spawning. Bound memory, CPU, process count, stdout/stderr size, and writable storage according to the backend. Terminate and reap the full process group after timeout.

Validate import and syntax policy before execution. Allowed imports: pandas, numpy, duckdb, requests, json, datetime, and math. An allowlisted module can still expose file, network, or code-execution capabilities; module-name filtering alone does not enforce isolation.

Prevent symlink escape from the assigned directory. Do not mount the main warehouse, project `.env`, home directory, or credentials into the sandbox. No unsafe fallback is allowed when the isolation backend is unavailable.

## API broker

Validate exact HTTPS catalog endpoints and plan parameters on the host. Do not follow redirects. Pass approved response snapshots into the sandbox. Restrict the generated Requests-compatible interface to those requests, with no fallback to real network access.

Add source shape validation, response limits during transfer, timeouts, and bounded retries. Keep source strings as data; never execute instructions embedded in responses.

## SQL permissions

| Operation | Agent-owned target | Other tables |
| --- | --- | --- |
| SELECT | Permit authorized reads | Permit only explicitly authorized reads |
| CREATE TABLE | Permit an approved new target | Reject replacing an existing nonowned object |
| INSERT / UPDATE / MERGE | Permit within pipeline scope | Reject unless explicitly authorized |
| DELETE | Permit only scoped idempotent replacement | Reject unless explicitly authorized |
| ALTER | Permit approved, validated migrations | Reject unless explicitly authorized |
| DROP / TRUNCATE | Deny by default; require explicit trusted permission | Require explicit trusted permission |
| Metadata writes | Trusted host code only | Trusted host code only |
| COPY / ATTACH / extension operations / security-changing SET or PRAGMA | Reject from generated SQL | Reject from generated SQL |

This policy is stricter than merely blocking a few destructive keywords. Parse SQL with a DuckDB-aware parser, verify identifiers and referenced objects, inspect complete statements, and disable DuckDB external access in the execution context. Comments, quoting, nested queries, and additional statements must not bypass the checks.

Generated code loads a staging database. Trusted publishing code performs warehouse mutations after validation. Successful validation does not authorize touching unrelated tables.

## Logs and artifacts

Log action summaries and sanitized arguments, not hidden reasoning or authentication headers. Prompt caches and reports can contain user-provided details; keep them local and exclude runtime artifacts from version control. Limit samples and avoid dumping entire datasets into logs or repair prompts.

Do not claim these controls are effective until the denial cases in [testing.md](testing.md) pass on the supported execution backend.
