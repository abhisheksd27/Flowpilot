# Bengaluru daily walkthrough

A user requests Bengaluru weather and air quality. FlowPilot resolves the city, records its coordinates and Asia/Kolkata timezone, and plans weather plus PM2.5 ingestion. The broker saves raw Open-Meteo responses, while isolated generated Python merges their hourly arrays into the canonical staging table.

Independent checks reject gaps, nulls, invalid values and source mismatches. A successful transaction merges silver rows by city/time and refreshes local-date gold summaries. Anomaly detection evaluates temperature, humidity and PM2.5 using Z-score and IQR, then writes an attributable Markdown report.

The verified live run published 139 hourly records and six daily summaries, with one PM2.5 statistical flag. An overlapping rerun published the same keys with zero additional rows. These counts describe that run, not a promise for every future window. The daily service repeats the same workflow at 08:00 Asia/Kolkata.
