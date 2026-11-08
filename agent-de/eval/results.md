# Failure-injection evaluation

Mode: deterministic HTTP/model fixtures; real transformations, Pandera checks, DuckDB transactions, and LangGraph routing. The fixture executor is not evidence of OS isolation or live LLM quality.

| Scenario | Outcome | Graph retries | Seconds |
| --- | --- | ---: | ---: |
| renamed_field | Recovered | 1 | 0.25 |
| removed_field | Recovered | 1 | 0.22 |
| new_field | Recovered | 2 | 0.25 |
| type_change | Recovered | 1 | 0.21 |
| null_spike | Recovered | 1 | 0.22 |
| duplicate_rows | Recovered | 2 | 0.25 |
| api_timeout | Recovered | 1 | 0.21 |
| malformed_json | Recovered | 1 | 0.21 |
| out_of_range | Recovered | 1 | 0.21 |

Self-heal success rate: **100.0%** (9/9 recoverable scenarios).

Persistent-failure preservation and sandbox boundaries are covered separately by pytest.
