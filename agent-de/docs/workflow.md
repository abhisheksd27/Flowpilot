# Workflow

1. Validate the request and plan against the weather/air-quality catalog; resolve the city through geocoding.
2. Generate a full transformation program. Validate its syntax and policy before execution.
3. Fetch weather and air quality, using bounded HTTP retries and expiring disk cache. Save source URLs, parameters, retrieval times and hashes under bronze/run_id.
4. Execute against approved snapshots in an OS sandbox; write only an attempt staging database.
5. Check strict schema, nonempty data, nulls, finite numbers, ranges, unique location/time keys, freshness, complete hourly coverage, accepted schema, and every value against trusted source transformation.
6. On failure, propose a distinct bounded repair: verified field alias, numeric conversion, identical duplicate removal, accepted source schema update, or one fresh fetch. Conflicting duplicates, unsafe code, persistent missing values and invented measurements fail safely.
7. Publish validated data transactionally. Detect Z-score and IQR anomalies and write a Markdown report.

State includes request, plan, generated code, snapshots, validation, errors, fixes, retry_count, step_history, schema drift, published counts, anomalies and final report. Logs contain concise action summaries, not private model reasoning. Each run saves code, result JSON, raw snapshots, logs and report. Failures preserve previously published data; anomalies run after publication.
