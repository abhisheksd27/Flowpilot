# Setup

Requires Python 3.11 and macOS sandbox-exec, or Linux with Docker. Run from agent-de:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python main.py run --provider builtin
streamlit run app.py
```

Built-in mode requires network access but no API key. For Gemini or Groq, set the respective key/model in .env and choose the provider. Ollama requires its local server and installed configured model. Shell environment overrides .env. Never commit secrets.

For Docker isolation:

```bash
docker build -f Dockerfile.sandbox -t agent-de-sandbox:local .
```

Set SANDBOX_BACKEND=docker and check SANDBOX_IMAGE in .env.example matches the built image. The worker has no network; the host fetches all inputs. Dependencies have bounded ranges; requirements.lock.txt records the verified environment.

Consult `.env.example` for cache TTLs, request timeout/backoff, sandbox limits, DATA_DIR and daily schedule. The built-in default request tracks Bengaluru weather and air quality.
