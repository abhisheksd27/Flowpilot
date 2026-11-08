# Free interview deployment

Deploy the repository's render.yaml as a Render Blueprint, or configure an existing Python web service:

- Root directory: agent-de
- Build: pip install -r requirements.txt
- Start: streamlit run app.py --server.address 0.0.0.0 --server.port $PORT
- Environment: DEMO_MODE=true, LLM_PROVIDER=builtin, OPENBLAS_NUM_THREADS=1, OMP_NUM_THREADS=1, PYTHON_VERSION=3.11.11
- Instance: Free

Save the environment settings and deploy the latest main commit. Open the service's onrender.com URL. Select a city, enter “Track weather and air quality in Bengaluru”, and click Refresh data now. Results show the latest completed hourly measurement, not an instantaneous thermometer reading.

The demo fetches real Open-Meteo inputs and retains staging, validation, transactional publication, anomaly analysis, reports and actual workflow events. It accepts only exact repository-owned transformation templates and calls trusted Python functions; it never executes model-generated code. No credentials or Docker are required. Requests remain within the weather and air-quality dataset contract, rather than arbitrary chat questions.

AI providers and the OS sandbox remain available by setting DEMO_MODE=false on an appropriately provisioned host with Docker. Public demo runs share a single warehouse and use its existing single-writer lock; simultaneous runs may need retrying. Free hosting may sleep, is resource limited, and provides ephemeral storage. Use the separate GitHub hourly dashboard for published scheduled results.
