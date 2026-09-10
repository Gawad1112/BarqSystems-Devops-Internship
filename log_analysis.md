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

---

## Method and conventions

All three logs were analysed read-only. Baseline SHA256 checksums were recorded before
any analysis began and are stored in `analysis/logs_sha256_before.txt`. They are
re-verified at the end of this document to prove the originals were never modified.

`logs/access.log` and `logs/application.log` are newline-delimited JSON.
`logs/error.log` is plain text.

**Every jq command below uses `-R` with `fromjson?`** rather than parsing the files as a
JSON stream. `-R` reads each line as a raw string, `fromjson` parses that string, and
the `?` operator discards lines that fail to parse and continues.

This is not cosmetic. jq's default behaviour is to treat a file as one continuous JSON
value stream and **abort** at the first invalid line. With one truncated line in each
file, the default silently processed only the first 312 lines of access.log and the
first 401 of application.log, then returned a plausible but wrong answer with no
indication of truncation. The first interval measurement was 17 minutes short as a
result. See troubleshooting.md Entry 8.

**Timestamp handling.** access.log and application.log use ISO 8601 UTC with fields
ordered largest unit to smallest and zero-padded to fixed width, so lexical sort order
is identical to chronological order. This would not hold for a format such as
`20/08/2026`, where the day would sort before the year. error.log uses
`2026/08/20 11:05:02` — different notation, same clock. `logs/README.md` states all
three files are UTC.

**Instance mapping**, proven rather than assumed — see Q4:
`172.23.0.11 = app-01`, `172.23.0.12 = app-02`.

---

## Commands / scripts

You can find commands below with each answer as i prefered for each command to be next to the related output rather than collecting them here.

---

## Results

### Q1. UTC interval, and valid / malformed / duplicate lines per file

**Interval: 2026-08-20 11:00:00Z to 11:30:00Z — 30 minutes.**

| log | first record | last record |
|---|---|---|
| access.log | 2026-08-20T11:00:00.015Z | 2026-08-20T11:29:57.578Z |
| application.log | 2026-08-20T11:00:00.015Z | 2026-08-20T11:29:57.578Z |
| error.log | 2026/08/20 11:05:02 | 2026/08/20 11:30:00 |

```bash
jq -R -r 'fromjson? | select(.timestamp) | .timestamp' logs/access.log | sort | head -1
jq -R -r 'fromjson? | select(.timestamp) | .timestamp' logs/access.log | sort | tail -1
jq -R -r 'fromjson? | select(.timestamp) | .timestamp' logs/application.log | sort | head -1
jq -R -r 'fromjson? | select(.timestamp) | .timestamp' logs/application.log | sort | tail -1
head -1 logs/error.log | cut -d' ' -f1-2
tail -1 logs/error.log | cut -d' ' -f1-2
```

access.log and application.log begin and end on the same millisecond, as expected for
two views of the same traffic. error.log begins 5 minutes 2 seconds later because no
failure had occurred before that point, and its final line is a
`log collector rotated stream` notice rather than an error.

*Limitation:* the error.log interval was taken with `head -1` / `tail -1`, which assumes
the file is in chronological order. Normal for a log, but assumed rather than verified.
Note that access.log is demonstrably **not** perfectly ordered — its malformed line 311
carries a timestamp earlier than line 310 (see below).

**Line counts**

| | access.log | application.log | error.log |
|---|---|---|---|
| total lines | 726 | 730 | 68 |
| valid JSON | 725 | 729 | n/a (not JSON) |
| malformed | 1 (line 311) | 1 (line 401) | 0 |
| byte-identical duplicate lines | 5 | 2 | 0 |
| request_ids appearing more than once | 5 | 49 | — |
| distinct request_ids | 720 | 680 | — |

```bash
# Total lines. grep -c '' counts lines; wc -l counts newline characters and
# undercounts by one if a file does not end with a newline. Both agreed here.
grep -c '' logs/access.log          # 726
grep -c '' logs/application.log     # 730
grep -c '' logs/error.log           # 68

# Valid JSON lines
jq -R -r 'fromjson? | "ok"' logs/access.log | wc -l          # 725
jq -R -r 'fromjson? | "ok"' logs/application.log | wc -l     # 729

# Byte-identical duplicate lines. The sort is mandatory: uniq only compares
# each line to the one immediately before it, so without sorting, duplicates
# that are not adjacent are silently missed and the answer looks plausible.
sort logs/access.log | uniq -d | wc -l          # 5
sort logs/application.log | uniq -d | wc -l     # 2

# Repeated request_ids
jq -R -r 'fromjson? | select(.request_id) | .request_id' logs/access.log | sort | uniq -d | wc -l        # 5
jq -R -r 'fromjson? | select(.request_id) | .request_id' logs/application.log | sort | uniq -d | wc -l   # 49

# Distinct request_ids
jq -R -r 'fromjson? | select(.request_id) | .request_id' logs/access.log | sort -u | wc -l        # 720
jq -R -r 'fromjson? | select(.request_id) | .request_id' logs/application.log | sort -u | wc -l   # 680
```

The arithmetic closes in both files with nothing unaccounted for:
- access.log: 725 valid = 720 distinct + 5 replayed
- application.log: 729 valid = 680 distinct + 49 repeated

**Definition of malformed:** a line that does not parse as valid JSON. Objective and
re-runnable.

**Locating them.** Each line was parsed independently, because a stream parser reports
where it gave up rather than where the defect is:

```bash
i=0
while IFS= read -r line; do
  i=$((i+1))
  printf '%s\n' "$line" | jq -e . >/dev/null 2>&1 || echo "MALFORMED access.log line $i"
done < logs/access.log
# -> MALFORMED access.log line 311
```

The same loop against application.log reports line 401.

**What the malformed lines are.** Both are truncated mid-record:
access.log line 311 50 bytes (neighbouring lines: 210)
{"timestamp":"2026-08-20T11:12:48Z","request_id":

application.log line 401 45 bytes (neighbouring lines: 203)
{"timestamp":"2026-08-20T11:17:00Z","event":

Each stops immediately after a key and its colon, with no value and no closing brace —
a partial write, roughly a quarter of a normal record. Both also carry whole-second
timestamps (`11:12:48Z`) where every normal record has milliseconds, and access.log
line 311 is out of chronological order relative to line 310 (`11:12:49.525Z`).

**Why jq blamed line 313 when the defect is at line 311.** jq's error was
`Expected separator between values at line 313, column 1`. A truncated line leaves the
parser expecting a value. The next line begins with `{`, which is a legal start of a
value, so the parser consumes that entire good record as the value of `"request_id"`.
Only at the line after that does it find something illegal. Confirmed by supplying the
missing closing brace:

```bash
{ sed -n '311,312p' logs/access.log; echo '}'; } | jq .
```

This parses as a single object with line 312's whole record nested inside the
`"request_id"` field. **One truncated line makes a second, valid line unreadable to a
stream parser.** Per-line parsing recovers it, which is why the valid count is 725 and
not 724.

**Parse exclusions:** 1 line excluded from access.log (line 311) and 1 from
application.log (line 401). Neither contains a recoverable request_id — both truncate
before the value — so no request data is lost by discarding them. No other lines were
excluded from any count in this document.

**What the duplicates are.**

The 5 duplicated lines in access.log are byte-identical `GET /` 200 records timestamped
at 11:05:00, 11:10:00, 11:15:00, 11:20:00 and 11:25:00 — exactly every five minutes, on
the minute:

```bash
sort logs/access.log | uniq -c | sort -rn | head -5
```

This is consistent with the `log collector rotated stream` notice in error.log: the
collector appears to have re-emitted the in-flight record at each rotation. Stated as
*consistent with* rather than proven, because the rotation notice appears once in
error.log (at 11:30) rather than five times.

application.log is a different case: 49 repeated request_ids but only 2 byte-identical
lines. The other 47 are not duplicates at all — see Q2.

---

### Q2. Distinct client requests, and how retries were not double-counted

**720 distinct client requests**, taken from access.log.

```bash
jq -R -r 'fromjson? | select(.request_id) | .request_id' logs/access.log | sort -u | wc -l
# -> 720
```

Deduplication method: parse each line independently, extract `request_id`, `sort -u`.

**Three ways this count could have been wrong, and how each was avoided.**

**1. Adding the two logs together, or counting requests from application.log.**

access.log is written by NGINX and records **client requests** (720). application.log is
written by the Flask applications and records **requests that reached an application**
(680). These are different populations, not two halves of one.

The 40-request difference is not missing data. Those 40 requests never reached any
application, because NGINX could not connect to the backend they were routed to:

```bash
comm -23 \
  <(jq -R -r 'fromjson? | select(.request_id) | .request_id' logs/access.log | sort -u) \
  <(jq -R -r 'fromjson? | select(.request_id) | .request_id' logs/application.log | sort -u) \
  | tee analysis/access_only_ids.txt | wc -l
# -> 40

grep -Ff analysis/access_only_ids.txt logs/error.log | wc -l
# -> 40, every one "connect() failed (111: Connection refused)"

grep -Ff analysis/access_only_ids.txt logs/access.log | jq -R -r 'fromjson? | .status' | sort | uniq -c
# -> 40 502
```

Three independent counts agree: 40 request_ids present in access.log and absent from
application.log, 40 matching connection failures in error.log, 40 client responses of
502. The absence of application-side records is evidence of what happened, not a gap in
the data.

**2. Counting application.log lines as requests.** The file contains two event types:

```bash
jq -R -r 'fromjson? | .event' logs/application.log | sort | uniq -c
#   47 dependency_error
#  682 http_request
```

47 of the 729 valid lines are `dependency_error` records. They describe a failing
downstream dependency and carry no method, path, status or duration. Each shares its
`request_id` with an `http_request` record for the same request — so a naive count of
repeated request_ids reads these as duplicates. They are not. They are **two different
kinds of record about one request**.

Example (`lab-000292`), one millisecond apart, same instance:
{"timestamp": "2026-08-20T11:12:09.524Z", "level": "ERROR", "event": "dependency_error",
"request_id": "lab-000292", "instance_id": "app-02", "dependency": "redis",
"error_type": "TimeoutError"}

{"timestamp": "2026-08-20T11:12:09.525Z", "level": "WARN", "event": "http_request",
"request_id": "lab-000292", "instance_id": "app-02", "method": "GET", "path": "/ready",
"status": 503, "duration_ms": 2025.0}
Verified that every dependency error pairs with a request record, and none stands alone:

```bash
comm -23 \
  <(jq -R -r 'fromjson? | select(.event=="dependency_error") | .request_id' logs/application.log | sort -u) \
  <(jq -R -r 'fromjson? | select(.event=="http_request")     | .request_id' logs/application.log | sort -u) | wc -l
# -> 0    no dependency error without a matching request record

comm -12 \
  <(jq -R -r 'fromjson? | select(.event=="dependency_error") | .request_id' logs/application.log | sort -u) \
  <(jq -R -r 'fromjson? | select(.event=="http_request")     | .request_id' logs/application.log | sort -u) | wc -l
# -> 47   every dependency error pairs with exactly one request record
```

So any count taken from application.log must filter on `event == "http_request"` first:

```bash
jq -R -r 'fromjson? | select(.event=="http_request") | .request_id' logs/application.log | sort -u | wc -l
# -> 680   (682 http_request lines minus the 2 byte-identical replays)
```

**3. Counting NGINX retries as separate requests.** `logs/README.md` states that
comma-separated upstream values describe multiple attempts for one client request.
NGINX writes **one** access line per client request regardless of how many backend
attempts it made; the attempts appear as comma-separated values within that one line.
19 requests were retried (Q6). Because each is a single line, deduplicating on
request_id counts them once — which is correct, since the client made one request.

The reciprocal trap is that a retried request may be logged **twice** in
application.log, once by each instance that handled an attempt. This is a further
reason not to derive a client-request count from the application log.

---

### Q3. Final client status counts, error rate and denominator

**Denominator: 720 distinct client requests.** access.log, valid lines only, one entry
per request_id. Not 725, which counts the 5 collector replays twice. Not 726, which
includes the truncated line.

| status | count | share of 720 |
|---|---|---|
| 200 | 615 | 85.42% |
| 404 | 10 | 1.39% |
| 502 | 40 | 5.56% |
| 503 | 47 | 6.53% |
| 504 | 8 | 1.11% |
| **total** | **720** | 100% |

```bash
jq -R -r 'fromjson? | select(.request_id and .status) | .request_id + " " + (.status|tostring)' logs/access.log \
  | sort -u | awk '{print $2}' | sort | uniq -c
```

Before deduplication the same command yields 620 × 200 (total 725). The 5 collector
replays were all `GET /` with status 200, which accounts for the difference.

Safety check — no request_id carries two different statuses, which would have inflated
the deduplicated count rather than reducing it:

```bash
jq -R -r 'fromjson? | select(.request_id and .status) | .request_id + " " + (.status|tostring)' logs/access.log \
  | sort -u | cut -d' ' -f1 | uniq -d
# -> no output
```

**Two error rates, measuring different things:**

- **5xx error rate: 95 / 720 = 13.19%** — requests the system failed to serve.
- **4xx + 5xx failure rate: 105 / 720 = 14.58%** — all non-successful responses.

```bash
jq -R -r 'fromjson? | select(.request_id and .status) | .request_id + " " + (.status|tostring)' logs/access.log \
  | sort -u | awk '{print $2}' | grep -c '^5'      # 95
jq -R -r 'fromjson? | select(.request_id and .status) | .request_id + " " + (.status|tostring)' logs/access.log \
  | sort -u | awk '{print $2}' | grep -Ec '^[45]'  # 105

echo "scale=2; 95 * 100 / 720" | bc -l    # 13.19
echo "scale=2; 105 * 100 / 720" | bc -l   # 14.58
```

*Note on `bc`:* `scale` limits digits during **division**, and applies at each step of
the expression. Writing `95 / 720 * 100` truncates to `0.13` before multiplying and
returns `13.00`. Multiplying before dividing (`95 * 100 / 720`) preserves the
significant digits. This is the second tool in this analysis to return a plausible
wrong number without any warning, after the jq stream abort.

**I report 13.19% as the incident error rate.** A 5xx means the server failed to do
something it should have done. A 404 means the server worked correctly and told the
client that what it asked for does not exist — the fault is in the request, not the
service. Grouping them measures two different things.

The 404s support treating them separately. All 10 are `GET /missing`, spaced ~197–198
seconds apart (3m17s–3m18s) across the entire 30 minutes, alternating between app-01 and
app-02, and logged by both applications at WARN level:

```bash
jq -R -r 'fromjson? | select(.path=="/missing") | .timestamp[11:19] + " " + (.status|tostring)' logs/access.log
# 11:00:00 404   11:03:17 404   11:06:35 404   11:09:52 404   11:13:10 404
# 11:16:27 404   11:19:45 404   11:23:02 404   11:26:20 404   11:29:37 404

jq -R -r 'fromjson? | select(.path=="/missing") | .timestamp[11:19] + " " + .level + " " + .instance_id' logs/application.log
# 11:00:00 WARN app-01   11:03:17 WARN app-02   ... alternating throughout
```

That regularity is an automated caller — most plausibly a misconfigured monitor —
polling a route that does not exist. It is present before the first incident begins and
continues after the last one ends, so it is uncorrelated with any incident. Including
it would make the error rate non-zero during the 20 minutes when nothing was wrong, and
a metric that never reads zero on a healthy system is a poor incident metric. It is
nonetheless a real configuration fault and is reported separately rather than dismissed.

---

### Q4. Which paths, time windows and backends account for the failures

**By time window — four discrete incidents, each with a clean start and end:**

```bash
jq -R -r 'fromjson? | select(.request_id and .status) | .request_id + " " + .timestamp[11:16] + " " + (.status|tostring)' logs/access.log \
  | sort -u | awk '$3 ~ /^5/ {print $2}' | sort | uniq -c
```
11:05 ████████ 8 ┐
11:06 ████████ 8 │ Incident 1 — app-02 refusing connections
11:07 ████████ 8 │ 40 × 502
11:08 ████████ 8 │
11:09 ████████ 8 ┘
11:10 (quiet)
11:11
11:12 ████████ 8 ┐
11:13 ███████ 7 │ Incident 2 — Redis TimeoutError
11:14 ████████ 8 │ 31 × 503
11:15 ████████ 8 ┘
11:16 (quiet)
11:17
11:18
11:19
11:20 ████████ 8 ┐ Incident 3 — PostgreSQL InvalidPassword
11:21 ████████ 8 ┘ 16 × 503
11:22 (quiet)
11:23
11:24
11:25 ████ 4 ┐ Incident 4 — upstream read timeout
11:26 ████ 4 ┘ 8 × 504
---
95

No 5xx before 11:05:02 or after 11:26:47.

| window | 5xx | status | paths affected | backend(s) |
|---|---|---|---|---|
| 11:05:02–11:09:57 | 40 | 502 | `/`, `/counter`, `/health`, `/records` | app-02 only |
| 11:12–11:15 | 31 | 503 | `/counter`, `/ready` | both |
| 11:20–11:21 | 16 | 503 | `/records`, `/ready` | both |
| 11:25:14–11:26:47 | 8 | 504 | `/records` only | both |

**By backend.** The IP-to-instance mapping was proven by correlation, not assumed. The 8
timed-out requests appear in both logs: the 4 whose access.log `upstream` is
`172.23.0.12:8080` have application.log records naming `app-02`, and the 4 with
`172.23.0.11:8080` name `app-01`. Independently, all 19 retried requests failed on
`.12` and succeeded on the other backend, and application.log names `app-01` for every
one. **Mapping: 172.23.0.11 = app-01, 172.23.0.12 = app-02.**

Incident 1 is confined to one backend — all 59 connection-refused errors name
`172.23.0.12:8080` and none name `.11`:

```bash
grep 'Connection refused' logs/error.log | grep -o 'upstream: "[^"]*"' | sort | uniq -c
#  10 .12:8080/     10 .12:8080/counter   10 .12:8080/health
#   9 .12:8080/instance   10 .12:8080/ready   10 .12:8080/records     = 59
```

Incident 4 affects both backends equally, and only `/records`:

```bash
grep 'Operation timed out' logs/error.log | grep -o 'upstream: "[^"]*"' | sort | uniq -c
#   4 .11:8080/records    4 .12:8080/records
```

error.log totals: 59 connection-refused + 8 timeouts + 1 rotation notice = 68 lines.

```bash
grep -o '([0-9]*: [^)]*)' logs/error.log | sort | uniq -c
#   8 (110: Operation timed out)
#  59 (111: Connection refused)
```

**By dependency (incidents 2 and 3).** The 47 dependency errors split cleanly by both
time and dependency, with no overlap in any minute:

```bash
jq -R -r 'fromjson? | select(.event=="dependency_error") | .timestamp[11:16] + " " + .dependency' logs/application.log \
  | sort | uniq -c
#   8 11:12 redis        8 11:20 postgres
#   7 11:13 redis        8 11:21 postgres
#   8 11:14 redis
#   8 11:15 redis
```

- `redis` / `TimeoutError`: 31 errors, window 11:12–11:15
- `postgres` / `InvalidPassword`: 16 errors, window 11:20–11:21

Joining each dependency error to the path of its matching request record:

```bash
jq -R -r 'fromjson? | select(.event=="dependency_error") | .request_id + " " + .dependency' logs/application.log | sort > analysis/dep_by_id.txt
jq -R -r 'fromjson? | select(.event=="http_request")     | .request_id + " " + .path'       logs/application.log | sort > analysis/path_by_id.txt
join analysis/dep_by_id.txt analysis/path_by_id.txt | awk '{print $2, $3}' | sort | uniq -c
#  16 redis /counter      8 postgres /records
#  15 redis /ready        8 postgres /ready
```

This matches the documented API contract exactly: `/counter` is Redis-backed,
`/records` is PostgreSQL-backed, and `/ready` checks **both** — which is why `/ready`
appears under each dependency. The logs corroborate the documented design rather than
contradicting it. Client-side, all 47 returned 503: 16 on `/counter`, 23 on `/ready`
(15 redis + 8 postgres), 8 on `/records`.

**Traffic was near-uniform across endpoints**, so the failure distribution reflects
which endpoints depend on what, not where traffic was concentrated:

```bash
jq -R -r 'fromjson? | select(.path) | .path' logs/access.log | sort | uniq -c
#  123 /          118 /counter   118 /health    119 /instance
#   10 /missing   118 /ready     119 /records                    = 725
```

---

### Q5. Median and p95 client latencies

**Median: 0.054 s (54 ms). p95: 2.001 s.**

**Field and units.** Taken from `request_time` in access.log, which NGINX records in
**seconds**. This is the closest available measure of what the client experienced: the
time from NGINX receiving the request to finishing the response.

application.log also carries latency, as `duration_ms` in **milliseconds**, but it
measures a different span — time spent inside the application, excluding NGINX's own
handling and connection setup. The two are not interchangeable, and incident 4 proves
it: `lab-000606` recorded `request_time: 2.001` in access.log and `duration_ms: 2700`
in application.log for the same request, a 700 ms disagreement. Mixing the two fields
would produce a meaningless distribution.

**Population: 720 distinct client requests** — the same denominator as Q3, deduplicated
on request_id so the 5 collector replays are not counted twice.

```bash
jq -R -r 'fromjson? | select(.request_id and .request_time) | .request_id + " " + (.request_time|tostring)' logs/access.log \
  | sort -u | awk '{print $2}' | sort -n > analysis/latencies.txt
wc -l < analysis/latencies.txt      # 720
```

**Percentile methods, stated explicitly.**

Median — the middle value of the sorted list. With an even count (720) there is no
single middle, so the two central values (ranks 360 and 361) are averaged. This is
linear interpolation between the two central observations.

```bash
awk '{a[NR]=$1} END {
  if (NR % 2) print a[(NR+1)/2];
  else print (a[NR/2] + a[NR/2+1]) / 2
}' analysis/latencies.txt
# -> 0.054
```

p95 — **nearest-rank method**: the smallest value in the sorted list such that at least
95% of observations are less than or equal to it. Rank = ceiling(0.95 × N) =
ceiling(684) = 684.

```bash
awk '{a[NR]=$1} END {
  r = 0.95 * NR;
  k = (r == int(r)) ? r : int(r) + 1;
  print "rank " k " of " NR ": " a[k]
}' analysis/latencies.txt
# -> rank 684 of 720: 2.001
```

Nearest-rank was chosen because it always returns an actual observed value rather than
an interpolated one that no request experienced. Other methods (linear interpolation
between ranks, as used by numpy's default percentile) would return a value between
0.12 and 2.001 here, which would be misleading — no request took 1.2 seconds.

**Why p95 lands in the failure population.** 105 of 720 requests (14.58%) were
non-successful, and nearly all of those were slow. Since 14.58% exceeds 5%, the 95th
percentile falls *inside* the failing group rather than at the top of the healthy one.
Rank 684 leaves 36 observations at or above it, and there are 39 values at 2.001 s or
higher (8 × 2.001 and 31 × 2.025), so rank 684 sits within the 2.001 block.

The practical reading: p95 here is not "the slow tail of normal traffic" — it is the
incident. A p95 of 2.001 s against a median of 0.054 s is a 37× gap, and that gap is
entirely explained by the four incidents in Q4.

**Range:** minimum 0.003 s, maximum 2.025 s.

**Distribution — the repeated values are the incidents, not noise:**

```bash
sort -n analysis/latencies.txt | uniq -c | sort -rn | head -10
```

| count | latency | what it is |
|---|---|---|
| 40 | 0.003 s | connection refused — instant TCP rejection, 502 |
| 31 | 2.025 s | Redis TimeoutError — full timeout budget burned, 503 |
| 24 | 0.041 s | 16 PostgreSQL InvalidPassword (503) + 8 unrelated successes |
| 19 | 0.120 s | retried requests — failed attempt plus successful one |
| ~9 each | 0.015–0.094 s | ordinary successful traffic |

**Three distinct failure speeds, each diagnostic of its mechanism:**

- **0.003 s** — nothing was listening. NGINX got an immediate TCP rejection and returned
  502 in 3 ms. A failure faster than any success.
- **0.041 s** — the dependency was reached and actively refused the credentials.
  PostgreSQL rejected the password immediately; there was nothing to wait for.
- **2.025 s** — the dependency was reached but never answered. The application waited
  out its full timeout before returning 503.

The 16 fast failures were confirmed as the PostgreSQL incident by time and path:

```bash
jq -R -r 'fromjson? | select(.request_id and .request_time == 0.041) | .request_id' logs/access.log | sort -u > analysis/lat041_ids.txt
grep -Ff analysis/lat041_ids.txt logs/access.log | jq -R -r 'fromjson? | .status' | sort | uniq -c
#   8 200    16 503
```

All 16 of the 503s fall between 11:20:07 and 11:21:45 on `/ready` and `/records`,
matching the 16 `postgres InvalidPassword` events exactly. The 8 successes are ordinary
requests spread across the full 30 minutes that happen to land on 0.041 s in the normal
latency cycle, and are unrelated.

This matters because **status code alone would have hidden the distinction.** All 47
dependency failures returned 503. Only the latency separates a timeout from a
rejection, and they are different faults requiring different fixes.

**Limitation.** The successful-request latencies are visibly synthetic: they step
through a fixed repeating cycle (0.015, 0.020, 0.023, 0.025, 0.028 …) rather than
forming a natural distribution, and `logs/README.md` states the data is synthetic lab
data. The percentile arithmetic is correct, but the median should not be read as a
measured service characteristic of a real system.

---

### Q6. Which requests retried upstream, and how many succeeded

**19 requests were retried. All 19 succeeded.**

```bash
grep -c '"upstream":"[^"]*,' logs/access.log
# -> 19

grep '"upstream":"[^"]*,' logs/access.log \
  | jq -R -r 'fromjson? | .timestamp[11:16] + "  " + .path + "  attempts=" + .upstream_status + "  client=" + (.status|tostring)'
# 11:05  /ready     attempts=502, 200  client=200
# 11:05  /instance  attempts=502, 200  client=200
# ... 19 lines, all identical in shape, all within 11:05-11:09
```

Every one shows `attempts=502, 200` and `client=200`: the first backend failed, the
second answered, the client received a success. All 19 fall within the connection-refused
window, and every one was ultimately served by **app-01**:

```bash
grep '"upstream":"[^"]*,' logs/access.log | jq -R -r 'fromjson? | .request_id' | sort -u > analysis/retry_ids.txt
grep -Ff analysis/retry_ids.txt logs/application.log \
  | jq -R -r 'fromjson? | select(.event=="http_request") | .request_id + " " + .instance_id' | sort
# -> all 19 report app-01
```

**Retry was applied to some endpoints and not others.** The 19 retried requests hit only
`/ready` (10) and `/instance` (9). The 40 requests that failed outright in the same
window hit only `/`, `/counter`, `/health` and `/records` — 10 each. The two sets are
disjoint:

```bash
grep '"upstream":"[^"]*,' logs/access.log | jq -R -r 'fromjson? | .path' | sort | uniq -c
#   9 /instance   10 /ready

grep -Ff analysis/access_only_ids.txt logs/access.log | jq -R -r 'fromjson? | .path' | sort | uniq -c
#  10 /   10 /counter   10 /health   10 /records
```

Both behaviours ran in parallel throughout the window — 8 non-retried and 4 retried in
every minute (3 in the final partial minute, which ended at 11:09:57) — which rules out
a configuration change partway through:

```bash
grep -Ff analysis/access_only_ids.txt logs/access.log | jq -R -r 'fromjson? | .timestamp[11:16]' | sort | uniq -c
#  8 11:05   8 11:06   8 11:07   8 11:08   8 11:09        = 40
grep '"upstream":"[^"]*,' logs/access.log | jq -R -r 'fromjson? | .timestamp[11:16]' | sort | uniq -c
#  4 11:05   4 11:06   4 11:07   4 11:08   3 11:09        = 19
```

8 + 4 = 12 per minute, matching the 12 errors per minute recorded in error.log for the
same window. The 2:1 ratio reflects 4 non-retried endpoints against 2 retried ones,
with traffic spread evenly across all six.

**Conclusion.** Retry was available and worked. A healthy backend was serving throughout
incident 1, and every request retried onto it succeeded. The 40 client-visible 502s were
requests to endpoints where retry was not applied. The endpoints that had retry
(`/ready`, `/instance`) are diagnostic; the endpoints that did not (`/`, `/records`,
`/counter`) are the ones users depend on.

This is behavioural evidence only. The historical `nginx.conf` was not supplied, so the
per-endpoint split is **consistent with** different `proxy_next_upstream` settings per
location block, but the configuration itself is not visible in the logs. See Q10.

---

## Timeline and correlated examples

## Evidence that the originals were unmodified

Baseline checksums were recorded before any analysis:

```bash
sha256sum logs/* | tee analysis/logs_sha256_before.txt
```

Re-verify at any time:

```bash
sha256sum -c analysis/logs_sha256_before.txt
```

`sha256sum -c` reads the recorded fingerprints and re-computes each file, reporting `OK`
or `FAILED` per file. Any single-character edit to a log would change its fingerprint
completely.

---

## Outstanding

- Q5 — median and p95 client latency, percentile method and units stated
- Q7 — full incident timeline across all three logs
- Q8 — correlated failed and successful request pair
- Q9 — proxy versus dependency classification
- Q10 — what the logs do not prove, and next checks in a running environment
