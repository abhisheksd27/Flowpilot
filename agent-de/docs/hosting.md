# Free public cloud deployment

Public dashboard: https://abhisheksd27.github.io/Flowpilot/

GitHub Actions runs the real pipeline hourly at minute 17 UTC (minute 47 IST), using the built-in engine and a network-isolated Docker worker. GitHub Pages serves the exported dashboard. The computer and external drive are not needed for cloud jobs. Scheduled Actions can be delayed and public schedules can be disabled after 60 days without repository activity; check the Actions page and re-enable when necessary.

The public dashboard is read-only. It shows the latest published result, validated tables, anomaly counts, quality checks, generated code, plan, and a replay of recorded flow events. It polls for updated snapshots every minute. Replay is labeled and never claims to be live execution. Manual runs require repository access through Actions → Hourly Bengaluru pipeline and dashboard → Run workflow. The local Streamlit app retains interactive controls and SQL exploration.

Each job restores the last published DuckDB checkpoint, performs validated upserts, and atomically deploys the new website with the updated checkpoint. Both dashboard JSON and the warehouse are public downloads. Transient restore errors stop the job; only HTTP 404 initializes the first warehouse. Raw source snapshots/logs are not public site assets. The runner is ephemeral; these raw artifacts are not retained after the job. Retain those separately if audit retention is required. Cloud and local warehouses are independent.

The workflow is `.github/workflows/hourly-pipeline.yml` at repository root. Public standard GitHub Actions runners and GitHub Pages can be used without a paid hosting plan; storage, bandwidth, acceptable-use and scheduling limits apply. No LLM secret is required. The 200 MB checkpoint bound stops growth from silently exceeding this deployment design; add retention/archival before that point.

Sources: [Actions billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions), [schedule limits](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [Pages workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages).
