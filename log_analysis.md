# Log analysis

Use all three supplied logs. Answer every question with commands/scripts and actual output.

1. What UTC interval is covered? How many valid, malformed and duplicate lines are in each file?
2. How many distinct client requests occurred? How did you deduplicate and avoid counting retries twice?
3. What are the final client status counts and error rate? State your denominator.
4. Which paths, time windows and backends account for the failures?
5. What are the median and p95 client latencies? State the percentile method and units.
6. Which requests retried upstream? How many succeeded after retrying?
7. Build an incident timeline using evidence from access, error AND application logs.
8. Show one correlated failed request and one successful request. Include IDs and timestamps.
9. Which errors appear to be proxy/connectivity issues versus dependency/application issues? What proves it?
10. What do the logs not prove? What would you check next in a running environment?

## Commands / scripts
### Q1 — interval

```bash
jq -R -r 'fromjson? | select(.timestamp) | .timestamp' logs/access.log | sort | head -1
jq -R -r 'fromjson? | select(.timestamp) | .timestamp' logs/access.log | sort | tail -1
jq -R -r 'fromjson? | select(.timestamp) | .timestamp' logs/application.log | sort | head -1
jq -R -r 'fromjson? | select(.timestamp) | .timestamp' logs/application.log | sort | tail -1
head -1 logs/error.log | cut -d' ' -f1-2
tail -1 logs/error.log | cut -d' ' -f1-2
```

`-R` reads each line as a raw string; `fromjson` parses it; `?` discards lines that
fail to parse instead of aborting the run. Without `-R ... fromjson?`, a single
malformed line silently truncates the result — see troubleshooting.md Entry 8.
## Results
### Q1 — UTC interval covered

All three logs cover 2026-08-20, 11:00:00Z to 11:30:00Z (30 minutes).

| log | first record | last record |
|---|---|---|
| access.log | 2026-08-20T11:00:00.015Z | 2026-08-20T11:29:57.578Z |
| application.log | 2026-08-20T11:00:00.015Z | 2026-08-20T11:29:57.578Z |
| error.log | 2026/08/20 11:05:02 | 2026/08/20 11:30:00 |

access.log and application.log begin and end on the same millisecond, as expected
for two views of the same traffic. error.log begins 5 minutes and 2 seconds later,
because no failures had occurred before that point, and its final line is a
`log collector rotated stream` notice rather than an error.

error.log uses a different timestamp notation (`2026/08/20 11:05:02` — slashes,
a space instead of `T`, no trailing `Z`). logs/README.md states all three files
are UTC; the formats differ but the clock does not.

Method note: the timestamps are ISO 8601 with fields ordered largest unit to
smallest and zero-padded to fixed width, so lexical sort order is identical to
chronological order. This would not hold for a format such as `20/08/2026`.

Limitation: the error.log interval was taken with `head -1` / `tail -1`, which
assumes the file is already in chronological order. This is normal for a log
but was assumed, not verified.
## Timeline and correlated examples
## Conclusions and limits


