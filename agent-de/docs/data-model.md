# Data model

Bronze: immutable JSON weather and air-quality responses in data/bronze/<run_id> with provenance and SHA-256 hashes.

Silver: `silver_environment`. Business key `(location_id, time)`; UTC timestamp `time`, text `location_id` and `city`, doubles `temperature_c`, `humidity_pct`, `pm2_5_ug_m3`, plus `run_id` and `ingested_at`. Fetch five previous days plus today, retaining only completed UTC hours. Upserts update overlapping keys while retaining older history.

Gold: `gold_daily_environment`. Local-date averages per location, sample counts, timezone, completion marker and run provenance. Bengaluru uses Asia/Kolkata. A day is complete when it is before today and has at least 24 samples; boundary dates and the current day remain explicitly incomplete. This completeness convention targets Bengaluru; DST locations need a variable expected-hour contract.

Metadata: `_agent_tables` owns publish targets; `_agent_schemas` stores accepted source/target schemas and versions; `_agent_schema_events` records drift; `_agent_runs` stores history. Source schema evolution preserves the fixed canonical output. Arbitrary target-table migrations are deliberately unsupported and fail validation.

Quality bounds: temperature −60 to 60 °C, relative humidity 0–100%, nonnegative PM2.5. Every staged measurement must reconcile to the brokered source. Open-Meteo weather and CAMS air-quality data are modeled estimates/forecasts, not direct station observations. Statistical outliers are not confirmed pollution incidents.
