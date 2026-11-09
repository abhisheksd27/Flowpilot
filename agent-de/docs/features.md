# Weather and pipeline workspace

Run the full runtime with Docker Desktop active:

```bash
cd agent-de
sh scripts/build-sandbox.sh
sh scripts/run-local-docker.sh
```

Open http://localhost:8504. The weather question field stays at the top. Expanded tools live under **Explore forecasts, data tools and pipeline operations**. All core pipeline runs retain schema, finite-value, coverage, duplicate, source-reconciliation and transactional publication checks.

## Weather questions and saved data

| Feature | Where / example | Behavior and scope |
| --- | --- | --- |
| Forecast questions | “Will it rain tomorrow in Bangalore?” / “Weather this weekend?” | Open-Meteo daily rain probability and high/low temperatures, explicit dates and retrieval time. Next-week forecasts are supported within the 14-day response. |
| Current conditions | “Is it sunny in Bangalore?” / “Humidity in Mumbai?” | Fresh modeled weather with time and units; handles daylight for sunshine questions. |
| Historical comparison | “Is today hotter than yesterday?” | Uses saved city-local daily means with hour counts; partial days are disclosed, not treated as complete. |
| Ask saved data | “How many hours exceeded 30°C last week?” | Compiles the supported question into a parameterized SELECT and shows SQL, parameters and coverage. Not an unrestricted natural-language SQL model. |
| City comparison | Explore data → Compare current conditions | Temperature, rain/showers and PM2.5 for two cities, with separate weather/air timestamps. |
| CSV export | Explore data → From/To → Load filtered records | City-local date filtering, UTC row timestamps, up to 366 days and 100,000 rows. Downloaded CSV identifies loaded city and dates. |
| Explain anomaly | Explore data → Explain an unusual reading | Current full-history Z-score/IQR baseline, threshold bounds and surrounding ±3 hours. Statistical flags are not confirmed incidents. |
| Additional source | Explore data → NASA solar-energy context | Fetch and save daily NASA POWER solar radiation; join to saved daily weather for comparison. This measures solar-energy availability, not electrical demand or power generation. NASA solar days and civil days differ. Missing NASA values remain unavailable. |

## Operations

| Feature | Where | Details |
| --- | --- | --- |
| Pipeline health | Hourly status / Operations | Last success, latest failure reason, next scheduled update, age of latest saved measurement. A three-hour freshness threshold is used. |
| Failure alerts | Dashboard banner/toast + Operations | Durable local alerts in data/alerts. Stale alerts clear after recovery; failure alerts retain history. Notifications require an open dashboard for immediate visibility; email/SMS is not configured. |
| Quality trends | Operations | Missing hours, duplicate keys, final failed checks and validation-attempt failures by run. “Not checked” stays distinct from zero. |
| Run comparison and metrics | Operations → First/Second run | Wall-clock duration, API calls, cache hits, repairs, row counts, errors. Uses up to 200 retained result files. |
| Lineage | Operations → Inspect selected run lineage | Source URL/parameters, input hashes/retrieval time, plan, exact transformation code, schema drift and validation outcome. |
| Schema changes | Lineage / Advanced results → History | Source diff and schema-decision metadata. Canonical output must remain valid before source drift is accepted. |
| Daily summary | Operations → Generate daily summary | Local daily temperature/humidity/PM2.5 averages, hour counts and recent run performance. Updated automatically after each successful run under data/summaries. |

## Pipeline configuration and recovery

Pipeline builder saves **one active pipeline configuration** to data/pipeline-config.json. Choose city, report measurements, hourly/daily schedule, daily time and a custom threshold rule. Built-in schema/coverage checks cannot be disabled. Measurement selection controls anomaly/report measurements; canonical warehouse columns remain intact.

Custom rules support above/below thresholds for temperature, humidity and PM2.5. A **flag** records matches without blocking valid source data. **Block** prevents publication when matched and preserves previously published data. Blocks are business decisions; a high real temperature is not automatically an invalid source value.

The watcher reads configuration at its next scheduled run and adopts its cadence. Saving configuration does not start another watcher. Do not run duplicate watchers. If no watcher is active:

```bash
sh scripts/watch-local-docker.sh
```

Scheduled runs use incremental mode: after the first collection they request only the recent hourly interval with a two-hour overlap for model revisions. First runs fetch the normal five-day window. Gaps outside the normal window require explicit backfills.

Recovery tools:

- **Validated backfill:** select UTC dates within the last 90 days. Fetches supported Open-Meteo history, checks full requested-hour coverage and upserts by city/timestamp. Historical time-boundary validation replaces the current freshness test only for this explicit mode; all remaining checks stay enabled. Both weather and air-quality availability are required. A provider coverage gap fails rather than fabricating data.
- **Replay failed run:** verifies archived snapshot hashes and reuses the original plan/window and code. Uses a new warehouse under data/replays. No live API request replaces the archived inputs. The replay may fail again if the original code/data remains invalid. Missing or archived snapshots are reported explicitly.
- **Failure simulation:** establishes a valid baseline from real inputs in data/simulations, injects a timeout/missing field/null into copied input, and tests transient or persistent failure. Shows recovery, row counts and baseline-value preservation. The main warehouse is untouched.

## API and storage

Start the read-only local API in another terminal:

```bash
source .venv/bin/activate
python -m pipeline.read_api --port 8765
```

Endpoints:

```text
GET http://127.0.0.1:8765/health?city=Bengaluru
GET http://127.0.0.1:8765/v1/weather?city=Bengaluru&start=2026-11-01&end=2026-11-09
```

The API binds only to localhost, limits data responses to 1,000 rows, validates city/date filters and exposes no arbitrary SQL or writes. It returns 503 if the warehouse is busy or unavailable. Public hosting requires separate authentication and request controls.

Storage & API provides a retention preview, manual archive, and optional automatic archiving after scheduled runs. Retention is bounded to 7–3650 days. Old raw snapshots, reports, logs and run directories move to **data/retention-trash**, preserving the warehouse, latest per-city results and latest successful runs. Restoring means moving them back to their original relative folder. This is recoverable archiving; it does not free disk space until you separately remove archives. Simulation/replay warehouses, summaries, alert history and extra-source files are not automatically removed by this policy. They remain available for inspection.

## Verified scope

Automated tests cover parameterized analytics, rule-blocked publication, incremental and historical windows, snapshot tampering, forecast-date selection, retention protection and the original pipeline/security suite. Live Docker verification covered baseline ingestion, a three-hour incremental interval, a 24-hour historical backfill, archived-input replay and transient/persistent missing-field simulations. Live calls verified Open-Meteo forecasts and NASA POWER solar radiation. Streamlit application checks verified rendering and filtered exports; the read API was verified over localhost HTTP.

Source contracts: [Open-Meteo forecast](https://open-meteo.com/en/docs), [air quality](https://open-meteo.com/en/docs/air-quality-api), [NASA POWER daily API](https://power.larc.nasa.gov/docs/services/api/temporal/daily/).
