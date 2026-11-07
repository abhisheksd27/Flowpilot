# Setup and Configuration

## Current setup status

The developer has completed environment setup. These instructions document how to reproduce it; repeating setup is not required to continue.

From the `agent-de` directory:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python --version
python -c "import duckdb, pandas, numpy, pandera, langgraph, streamlit, requests, dotenv, sqlglot, pytest; print('All dependencies imported successfully')"
```

Expected: Python 3.11.x and successful imports. On Windows, activate with `.venv\Scripts\Activate.ps1` in PowerShell instead.

## Environment file

If `.env` does not already exist, copy `.env.example` to `.env`. Do not overwrite an existing configured file. Never commit credentials. Edit the copied file locally.

`Settings.from_env()` loads the project `.env`; existing process environment variables take precedence. Relative `DATA_DIR` values resolve against the project directory, not the terminal's current directory. `Settings.prepare()` creates runtime subdirectories when explicitly called.

## Existing configuration

| Variable | Current example/default | Purpose |
| --- | --- | --- |
| `LLM_PROVIDER` | `ollama` | `gemini`, `groq`, or `ollama` |
| `GEMINI_API_KEY` | Empty | Gemini credential when selected |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Configurable model identifier |
| `GROQ_API_KEY` | Empty | Groq credential when selected |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | Configurable model identifier |
| `OLLAMA_URL` | `http://localhost:11434` | Local service address |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Model that must be installed locally |
| `DATA_DIR` | `./data` in example | Runtime files and warehouse location |
| `API_CACHE_TTL` | `900` | API cache lifetime in seconds |
| `LLM_CACHE_TTL` | `86400` | LLM cache lifetime in seconds |
| `HTTP_TIMEOUT` | `20` | API request timeout setting in seconds |
| `BACKOFF_SECONDS` | `1` | Base delay for exponential retries |
| `SANDBOX_BACKEND` | `auto` | Reserved setting for the future runner |
| `SANDBOX_IMAGE` | `agent-de-sandbox:local` | Reserved image name; image not provided yet |

Model names above describe the current configuration, not verified availability or free-tier entitlement. Choose an available model for your account when testing live integration.

`max_retries=3` and `python_timeout=30` are dataclass defaults in the current code, not environment variables. The LLM client currently uses a request timeout of at least 60 seconds. Neither Requests timeout setting is a total end-to-end run deadline.

## Provider selection

For Gemini, set `LLM_PROVIDER=gemini`, supply `GEMINI_API_KEY`, and configure `GEMINI_MODEL`.

For Groq, set `LLM_PROVIDER=groq`, supply `GROQ_API_KEY`, and configure `GROQ_MODEL`.

For Ollama, run a local Ollama service, install the model you select, and set `LLM_PROVIDER=ollama`, `OLLAMA_MODEL`, and `OLLAMA_URL`. No hosted API key is used by the existing local adapter.

Only configure the provider you intend to use. Tests will inject deterministic clients and must not need provider credentials.

## Configuration checks for the next coding step

Verify path resolution, environment precedence, invalid provider errors, missing key handling, and directory creation without printing a complete settings object containing secrets. Validate numeric settings before runtime: timeouts must be positive, cache TTLs nonnegative, and retry budgets bounded.

## Application commands

See the [README](../README.md) for planned entry points. The CLI, UI, tests, and evaluator must be implemented before those commands can produce application results. Sandbox setup will be documented against the actual chosen backend when that component exists.
