# Data Model and Schema Drift

This is a proposed contract, not a statement that these tables already exist.

## Example daily dataset

Default example target: `daily_environment`. Use a stable resolved location identifier instead of city name alone because names can be ambiguous.

| Field | Proposed DuckDB type | Meaning |
| --- | --- | --- |
| `location_id` | `VARCHAR` | Stable identifier recorded during location resolution |
| `city` | `VARCHAR` | Display name |
| `date` | `DATE` | Aggregation date in the recorded timezone |
| `timezone` | `VARCHAR` | Timezone used for daily boundaries |
| `temperature_c` | `DOUBLE` | Mean of valid hourly temperature readings |
| `humidity_pct` | `DOUBLE` | Mean of valid hourly relative-humidity readings |
| `pm2_5_ug_m3` | `DOUBLE` | Mean of valid hourly PM2.5 readings |
| `weather_samples` | `INTEGER` | Valid aligned weather samples used |
| `air_quality_samples` | `INTEGER` | Valid air-quality samples used |
| `ingested_at` | `TIMESTAMP` | UTC ingestion time |

Business key: `(location_id, date)`. This example supports one consistent daily definition per target table. A different timezone, aggregation, unit, or source interpretation requires a separate dataset definition or a documented migration. Hourly pipelines need an hourly timestamp key instead.

Fields depend on the validated request. A weather-only plan does not require a fabricated air-quality column. Persist source units, response timestamps, coordinates, and whether values are forecasts or modeled historical estimates in run metadata.

## Completeness and validation

Validate raw hourly structure before daily aggregation. Pandas aggregation can skip nulls and conceal a missing-data spike. Record valid sample counts and expected coverage, including partial days and daylight-saving transitions where applicable.

The plan must explicitly set acceptable missingness and coverage. Do not relax them after observing failures. The initial strict policy may reject missing required measurements; a more permissive policy must explain excluded or imputed observations.

Temperature range: -60 to 60 Celsius. Relative humidity: 0 to 100 percent. PM2.5: finite and nonnegative. Check timestamps against the source window, timezone, and forecast/historical interpretation. Do not reject valid future forecasts using an observation-only freshness rule.

## Metadata tables

| Proposed table | Key fields | Purpose |
| --- | --- | --- |
| `_agent_tables` | Table name, owner ID, creation time, business-key JSON | Trusted ownership registry |
| `_agent_schemas` | Dataset/source ID, kind, version, schema JSON, acceptance time | Versioned expected raw and target schemas |
| `_agent_schema_events` | Run ID, old/new version, diff JSON, diagnosis, outcome | Audit proposed, rejected, and applied changes |
| `_agent_runs` | Run ID, status, start/end, publish result, report/log paths | Run outcome and artifact references |

Only trusted host code writes metadata. Generated code cannot declare itself the owner of an existing table. Ownership persists across process restarts; a matching name is not proof of ownership.

## Drift detection

Compare added fields, removed fields, type changes, and possible renames. Detect raw source drift separately from output drift. Empty or all-null fields have uncertain types; do not immediately accept them as a new schema.

Examples of proposed handling:

- Rename: use a verified mapping and retain the canonical output name.
- Numeric strings: convert explicitly and fail on unexpected conversion loss.
- Added field: record and explicitly accept or ignore it without changing required outputs.
- Removed required field: recover from a justified source or fail; never invent values.
- Output type change: validate conversion and preserve the prior table version before migration.

Expected schemas change only after successful validation and publishing. A rejected candidate cannot become the next baseline.

## Transactional publishing

Check ownership, start a transaction, apply an approved migration, upsert validated records by key, update accepted metadata, and commit. Roll back the transaction on failure. Preserve records outside the incoming key set. Keep a snapshot or versioned copy for a structural migration that may lose information.

Store rejected-drift audit events separately from accepted schema updates so a rollback does not erase the record of a failed attempt. Repeated publishing of identical input must preserve row counts and metric values.
