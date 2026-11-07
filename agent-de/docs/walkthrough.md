# Example Request Walkthrough

This is an illustrative execution, not a record of a completed run. No measurements, timings, or repair outcomes below are presented as observed results.

## Request

> Track daily weather and air quality for Bengaluru and flag anomalies.

## 1. Interpret and plan

The planner selects geocoding, weather, and air-quality sources from the catalog. Resolve Bengaluru through geocoding and record the returned location identifier, coordinates, and timezone. If several locations match, state the chosen assumption clearly.

Record a common supported date window, daily aggregation, Celsius temperature, percent humidity, PM2.5 units, and a business key such as `(location_id, date)`. Label source forecast/model semantics. Suggest a daily schedule without creating a scheduled job.

The host validates the plan before any generated code runs.

## 2. Fetch and transform

The API broker obtains approved responses, using a fresh cache entry where appropriate. Inspect source fields and timestamp alignment. Pass snapshots into the sandbox through the restricted request interface.

Generated code aligns weather and air-quality timestamps, checks units and missingness, and aggregates by local date. Keep sample counts so a daily average cannot conceal a largely missing day. Write the result to the assigned staging DuckDB table.

## 3. Validate

Check keys, required numeric types, null percentages, ranges, coverage, date window, and source/output schema differences. Compare source freshness according to its forecast or historical meaning.

If all checks pass, publish transactionally and update accepted metadata. Preserve unrelated dates and tables.

## 4. Example repair branch

Suppose a deterministic failure fixture renames `temperature_2m` to `temperature`. The original transform fails or raw schema inspection reports a mismatch.

The fix prompt receives current code, the schema diff, failure details, and previous attempts. It proposes mapping the verified replacement field back to the canonical output, with a short diagnosis. The host checks that this is distinct and permitted, then reruns in staging.

Only successful validation permits publishing. The report records the source change and repair. This illustrates a test scenario; it does not claim Open-Meteo actually renamed this field.

If the required temperature data is entirely unavailable, a rename fix cannot recover it. After bounded attempts, report failure and retain previous warehouse data.

## 5. Analyze

Read validated measurements and calculate configured z-score and IQR statistics. Daily source coverage may provide too few samples for a useful baseline. If so, report insufficient data rather than inventing a confidence level or treating an empty result as proof of normality.

Future reruns can build historical coverage if dataset definitions remain compatible. Never silently mix different units, timezones, locations, or aggregation rules into one baseline.

## 6. Present results

The UI displays the plan, current code, validation, anomalies/chart, final report, and a bounded table preview. The live log shows node progress and repair attempts. The user can download the Markdown report.

The report distinguishes fetched, staged, validated, and published records. It includes assumptions, source attribution, schema decisions, repairs, statistical limitations, usage counters, and the log path. If analysis fails after publishing, it states that data was published but analysis did not complete.
