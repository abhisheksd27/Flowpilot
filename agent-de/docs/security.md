# Execution and publication boundaries

Generated code passes AST checks, then runs in a separate OS-isolated process. AST/import restrictions alone are not the isolation boundary. macOS uses a deny-default sandbox-exec profile with runtime-library reads and writes only in the attempt directory; network and unrelated user-file access are denied. Docker uses no network, a read-only root, dropped capabilities, no-new-privileges, PID/CPU/memory limits and an attempt-only writable mount. Missing isolation fails closed.

Workers receive sanitized environment variables and approved JSON inputs, not provider credentials or the production warehouse. Execution timeout, CPU/file/output limits bound attempts. Docker enforces a 768 MB memory limit; macOS does not use RLIMIT_AS because that limit is unsupported there. The macOS sandbox-exec interface is deprecated; the container backend is preferable for portable deployments.

The API broker accepts exact HTTPS catalog hosts/paths and approved parameters, rejects redirects, bounds response size, and caches successful responses. SQL parses a single statement, disables DuckDB external access, and requires registered ownership for mutations; unscoped updates/deletes and destructive DDL need explicit trusted authorization. The UI SQL explorer is read-only.

Publication is a host-controlled transaction after independent quality checks and source-value reconciliation. Unknown target schema migrations, conflicting duplicates and unsafe repairs fail closed. The process lock prevents concurrent writers. Keep runtime data and secrets out of Git. This local single-user tool is not a multi-tenant security service.
