# BARQ DevOps Internship Task

A Flask API behind NGINX with PostgreSQL and Redis, supplied deliberately
broken and repaired here. This README contains copyable commands for every
operation, followed by answers to the assessment questions.

- Investigation journal: [troubleshooting.md](troubleshooting.md)
- Log analysis: [log_analysis.md](log_analysis.md)
- Technical decisions: [decisions.md](decisions.md)
- Security review: [security_review.md](security_review.md)
- Architecture: [architecture.png](architecture.png) (source: `architecture.dot`)
- AI disclosure: [AI_USAGE.md](AI_USAGE.md)

---

## Requirements

- Linux or WSL2, Docker with Compose v2, Python 3.12
- Host port 8080 free (8090 after the live port change)
- Container names `app-01`, `app-02`, `nginx`, `postgres`, `redis` unused

---

## Setup

```bash
git clone https://github.com/Gawad1112/BarqSystems-Devops-Internship.git
cd BarqSystems-Devops-Internship

# .env is gitignored and holds the database password.
# .env.example is tracked and carries placeholder values.
cp .env.example .env
```

Edit `.env` and set `POSTGRES_PASSWORD`, then set the same password inside
`DATABASE_URL`. They must match — a mismatch here was one of the supplied
faults.

Compose refuses to start if either `DATABASE_URL` or `REDIS_URL` is unset,
because both use the `${VAR:?message}` form. That is deliberate: an unset
variable fails loudly at parse time rather than silently becoming an empty
string and failing later as a confusing connection error.

## Build and start

```bash
# -p sets the project name. Required on EVERY compose command in this project.
docker compose -p barq-assessment up --build -d

docker compose -p barq-assessment ps
```

All five containers should report `Up`, with `(healthy)` on app-01, app-02,
postgres and redis.

## Stop and start

```bash
# Stop and remove containers. Volumes are NOT removed, so data survives.
docker compose -p barq-assessment down

# Start again
docker compose -p barq-assessment up -d
```

## Test the endpoints

```bash
curl -s http://127.0.0.1:8080/          # app response
curl -s http://127.0.0.1:8080/health    # liveness — process only
curl -s http://127.0.0.1:8080/ready     # readiness — postgres AND redis
curl -s http://127.0.0.1:8080/instance  # backend identity
curl -s http://127.0.0.1:8080/counter   # Redis INCR
curl -s http://127.0.0.1:8080/records   # PostgreSQL query

# Create a record
curl -s -X POST http://127.0.0.1:8080/records \
  -H "Content-Type: application/json" \
  -d '{"title":"example record"}'
```

Prove both backends serve traffic:

```bash
# 30 requests, not 6. NGINX runs one worker per CPU core and each worker keeps
# its own round-robin counter, so a small sample can return a single backend
# even when load balancing is working correctly. See Q1 below.
for i in $(seq 1 30); do
  curl -s http://127.0.0.1:8080/instance | grep -o 'app-0[12]'
done | sort | uniq -c
```

## Validation

```bash
python3 validate.py
echo "exit code: $?"
```

19 checks covering every endpoint, both backends, dependency readiness,
network isolation and prohibited host ports. Exits 0 on success, 1 on any
failure.

## Failure test

```bash
python3 failure_test.py
echo "exit code: $?"
```

Establishes a baseline, stops `app-02`, drives traffic for 15 seconds while it
is down, restores it and proves it serves again.

## Backup and restore

```bash
# Write a pg_dump to ./backups/ (gitignored — a dump contains every row)
./backup.sh

# Restore the most recent backup. Prints the file, size and timestamp, then
# pauses 3 seconds before overwriting the database.
./restore.sh

curl -s http://127.0.0.1:8080/records
```

## Persistence test

```bash
curl -s -X POST http://127.0.0.1:8080/records \
  -H "Content-Type: application/json" \
  -d '{"title":"persistence-proof"}'

curl -s http://127.0.0.1:8080/records

# Destroy and rebuild the app and database containers. The named volume
# postgres-data is NOT touched.
docker compose -p barq-assessment up -d --force-recreate app-01 app-02 postgres

# CREATED shows seconds for the recreated containers, and the original uptime
# for nginx and redis — proof only the targeted containers were replaced.
docker compose -p barq-assessment ps

sleep 10
curl -s http://127.0.0.1:8080/records   # the record is still there
```

## Cleanup

```bash
# Removes containers and networks. Volumes and data survive.
docker compose -p barq-assessment down

# Removes volumes too. THIS DESTROYS ALL DATA.
docker compose -p barq-assessment down -v
```

---

## Recorded challenge

`video_challenge.sh` is supplied by the assessment and must be run exactly
once, for the first time, during the video recording. It requires healthy
services, both initial instances and the target network layout.

```bash
./video_challenge.sh
```

The receipt is written to `.assessment/challenge.json`. Do not reset the
runtime challenge with `docker compose down`.

## Application-only tests

These use fake dependencies and do not exercise real SQL, Redis or Docker
networking, so they prove the application code works, not that the environment
is healthy.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
deactivate
```

---

# Assessment questions

## Q1. What failed first? What proved the cause? Which failed attempt taught you something?

**What failed first** was not part of the supplied environment at all. The
first `docker compose up` failed with
`ports are not available: exposing port TCP 127.0.0.1:8080`, and nginx never
started. My assumption was that this was one of the planted faults and the fix
would be somewhere in the project.

**What proved the cause** was looking on the correct side of the Windows/Linux
boundary. Docker publishes ports on the Windows host, so a conflict is not
visible from inside WSL. `netstat -ano | findstr :8080` in PowerShell returned
`LISTENING 5460`; `tasklist` resolved that to `rpdsvc.exe`, and a service query
identified it as RealPlayer Cloud Service — ordinary consumer software with no
connection to this project.

**The failed attempt that taught me something** was running
`netstat -ano | findstr :8080` inside WSL Ubuntu first, where both commands do
not exist. `findstr` is a Windows tool; Linux uses `grep`. That was the third
time on this project I had run a command in the wrong shell, after trying `wsl`
inside WSL and expecting Docker Desktop to be a Linux application.

The lesson was broader than the command. I had been treating every failure as
an intended part of the exercise, and looking for its cause inside the repo.
This one was not in the repo at all — it was my own machine, running software
that happened to want the same port. Real troubleshooting means being willing
to look outside the system you were handed, and knowing which environment a
command belongs to before running it.

There is a second lesson from the same incident, recorded in
troubleshooting.md Entry 3. I wrote up the fix as including a startup-type
change I had not actually made, and the port appeared free afterwards only
because the service was stopped for that session. A reboot three days later
showed it listening again. A fix verified only in the state that produced it
has not been verified at all.

Documented in troubleshooting.md Entry 3.

## Q2. What patterns did the logs reveal? How did you avoid double-counting requests?

**Four discrete incidents in 30 minutes**, each with a clean start and end and
quiet periods between:

| window | incident | client status | latency |
|---|---|---|---|
| 11:05:02–11:09:57 | app-02 refusing connections | 502 × 40 | 0.003 s |
| 11:12:09–11:15:52 | Redis TimeoutError | 503 × 31 | 2.025 s |
| 11:20:07–11:21:45 | PostgreSQL InvalidPassword | 503 × 16 | 0.041 s |
| 11:25:14–11:26:47 | upstream read timeout on /records | 504 × 8 | 2.001 s |

The latency column is the finding that status codes alone would have hidden.
Incidents 2 and 3 both returned 503, but a timeout burns its full budget
waiting while a credential rejection fails immediately. Three distinct failure
speeds — 3 ms for a refused connection, 41 ms for a rejection, 2 s for a
timeout — each diagnostic of a different mechanism.

**Deduplication: 720 distinct client requests**, from access.log, deduplicated
on `request_id` with `sort -u`. Three ways that count could have been wrong:

1. **Two logs, two populations.** access.log is written by NGINX and records
   client requests (720). application.log is written by the apps and records
   requests that *reached* an app (680). The 40-request difference is not
   missing data — those requests never reached any app, because NGINX could not
   connect. Three independent counts agree at exactly 40: request_ids present
   in one log and absent from the other, matching `connection refused` lines in
   error.log, and client responses of 502.

2. **Two record types in one file.** 47 of application.log's 729 valid lines
   are `dependency_error` records, not requests. Each shares a `request_id`
   with an `http_request` record, so a naive count of repeated IDs reads them as
   duplicates. Counts from that file must filter on `event == "http_request"`
   first.

3. **Retries are one line, not two.** NGINX writes one access line per client
   request regardless of how many backend attempts it made; the attempts appear
   as comma-separated values within that line. 19 requests were retried, all
   showing `502, 200`, and all 19 succeeded. Deduplicating on `request_id`
   counts them once, which is correct — the client made one request.

Full working in [log_analysis.md](log_analysis.md).

## Q3. How do requests flow? Why these ports, networks and readiness checks?
client → 127.0.0.1:8080 → nginx:80 → upstream pool → app-01:8080 / app-02:8080
↓
postgres:5432 / redis:6379


See [architecture.png](architecture.png).

**Ports.** Only NGINX is published, and it is bound to `127.0.0.1` rather than
`0.0.0.0`, so it is not reachable from other machines even on a trusted
network. PostgreSQL and Redis have no host mapping at all — `docker compose ps`
shows `5432/tcp` and `6379/tcp` with no host side. `validate.py` asserts that
5432, 6379, 8081 and 8082 are unreachable from the host, and CI runs that
assertion on every push, so a regression fails the build.

**Networks.** Two, with the apps on both. `frontend` carries NGINX and the
apps. `backend` carries the apps and the datastores and is declared
`internal: true`, so it has no route to the internet. NGINX is deliberately not
on `backend`: it is the only component exposed to untrusted input, so it is the
most likely thing to be compromised, and a compromise there should not have a
direct route to the database. Connections use service names, never container
IPs, because Docker assigns IPs at container start and they change on
recreation. `validate.py` asserts both directions — nginx **cannot** reach the
datastores, and app-01 **can**.

**Readiness checks.** `/health` and `/ready` answer different questions and
that separation is load-bearing. `/health` reports whether the process is
alive, and deliberately does not touch PostgreSQL or Redis. `/ready` returns
200 only if both dependencies respond. A container can therefore be healthy
while unable to serve real traffic, which is correct behaviour — liveness tells
you whether to restart something, readiness tells you whether to send it
traffic.

This distinction proved itself during an unplanned incident. The WSL2
filesystem was remounted read-only after an unclean shutdown, and PostgreSQL's
container healthcheck kept reporting `(healthy)` throughout, because
`pg_isready` only asks whether the server accepts connections and never touches
storage. `/ready` reported `postgres: unavailable` correctly. Container health
and application readiness are different signals, and only one of them was
telling the truth. See security_review.md finding 8.

## Q4. Why these timeouts, retries, restart settings and resource limits?

**Retries.** `proxy_next_upstream error timeout`, with
`proxy_next_upstream_tries 2` and `proxy_next_upstream_timeout 7s`.
`max_fails=3 fail_timeout=10s` on both upstream servers.

The supplied config had `max_fails=0` (failure counting disabled entirely, not
"stop after the first failure") and `proxy_next_upstream off`. The historical
logs quantify what that cost: 40 clients received 502s during incident 1 while
a healthy backend served throughout, and in the same window 19 requests on
`/ready` and `/instance` were retried and every one succeeded. Retry was
already working on two endpoints and absent on the four that users depend on.

`http_503` is deliberately **excluded** from the retry conditions. The 47
requests that returned 503 failed because Redis and PostgreSQL were failing,
and both app instances share the same Redis and the same PostgreSQL. Retrying
reaches the same broken dependency, fails identically, and doubles the load on
something already struggling. Retry is the right response to an instance-local
fault and the wrong response to a shared one.

`timeout` was the arguable inclusion, and it justified itself on the first live
test. Stopping a container does not produce uniform failures: one retried
request logged `502, 200` at 1.069 s (connection actively refused) and another
logged `504, 200` at 2.005 s — `proxy_connect_timeout` firing exactly, because
the packets were dropped rather than rejected. With `error` alone, that second
request would have returned 504 to the client.

**Timeouts.** `proxy_connect_timeout 2s`, `proxy_read_timeout 4s`.

The read timeout is tuned against a measured figure rather than a round number.
In incident 4, NGINX returned 504 after 2.001 s while the applications
completed those same requests successfully at 2700 ms. A read timeout below an
endpoint's real worst case manufactures failures out of successes. 4 s gives
1.3 s of margin over the observed 2700 ms; the inherited 3 s gave 300 ms.

The 7 s retry budget follows from the same number. With `tries 2` and a 4 s
read timeout the implied ceiling is 8 s, so a budget of 8 s would never fire.
7 s leaves the retry 3 seconds — deliberately more than the 2700 ms observed,
so the second attempt is capable of completing the slowest endpoint measured.
Worst case a client can experience: 4 s + 3 s = 7 s before an error.

**Restart policy.** `restart: unless-stopped`. The original `restart: "no"`
meant a single transient crash permanently removed one of two instances, and
the system would keep serving from the survivor — so the failure would be
silent, with no outage to alert on and no redundancy left. Verified after a
host reboot: both app containers were already running before any manual start.

**Resource limits.** 0.5 CPU and 256 MB per app instance. Verified applied:
`docker inspect app-01 --format '{{.HostConfig.Memory}} {{.HostConfig.NanoCpus}}'`
returns `268435456 500000000`. Limits contain a runaway instance so it cannot
starve the datastores or the other app on the same host.

Full reasoning in [decisions.md](decisions.md).

## Q5. When should validation fail? What does green CI prove, or not prove?

**Validation should fail** whenever the system cannot serve real traffic,
including cases where it superficially appears up. `validate.py` deliberately
checks behaviour rather than status codes alone:

- `/ready` must return 200 **and** both dependencies must report ready. A 200
  with a degraded dependency would otherwise pass silently.
- `/counter` must return a strictly greater value on a second call. A single
  call would pass against a hardcoded constant.
- A record created through `POST /records` must appear in a subsequent `GET`,
  proving a real database write rather than an echo of the request.
- An empty title must be **rejected** with 400. Validating only the happy path
  would miss an app that accepts anything.
- nginx must **not** be able to reach postgres or redis. This is a negative
  assertion, so it is paired with a positive one — nginx reaching app-01
  successfully — to prove `nc` works in that image and the failures are genuine
  isolation rather than a missing binary failing for the wrong reason.

Demonstrated rather than asserted: stopping redis produced exit code 1 with
`redis: unavailable` identified precisely; restarting it returned 19/19 and
exit 0.

**Green CI proves** the stack builds and runs from a clean checkout, on a
machine that has never seen this project, with no local state and placeholder
credentials — and that every check passes there.

**Green CI does not prove:**

- anything about the local environment. The CI database held 3 records where
  the local one held 7; they are independent.
- that the real credentials work. CI uses `change_me` from `.env.example`.
- anything about sustained behaviour. The whole run lasts 80 seconds; nothing
  here would catch a slow memory leak or a connection pool exhausting after
  hours.
- anything about load. Traffic is a few hundred sequential requests, not
  concurrent load.
- that the images are free of vulnerabilities. No scanning is configured — see
  security_review.md finding 9.

The failure test's own output illustrates the limit. It reported 100%
availability during the outage — zero errors — while throughput fell from 362
requests/second to 2. A check that counts errors cannot see a system that stays
up and crawls. Availability and usability are not the same measurement.

## Q6. Which single points of failure remain? How would you fix them in production?

**NGINX itself.** One instance, one container, no redundancy. If it stops,
everything is unreachable regardless of how many app instances are running. It now has a
healthcheck requesting `/health` through the upstream pool, so Docker reports
its state, but a healthcheck only reports a problem; it does not provide a
second instance to fail over to.
*Production:* multiple NGINX instances behind a load balancer or a managed
ingress, in different availability zones.

**PostgreSQL.** One instance with one volume. The volume protects against
container recreation, proven by test, but not against volume deletion, host
failure or logical corruption. `backup.sh` and `restore.sh` work — the restore
is proven in CI on every push — but they are run manually.
*Production:* streaming replication with an automatic failover mechanism,
scheduled backups stored off-host, and restores tested on a schedule rather
than assumed.

**Redis.** One instance. AOF persistence is enabled, so data survives a
restart, but not a host failure.
*Production:* Redis Sentinel or a managed service, and a decision about whether
the counter is data that must survive or a cache that may be rebuilt.

**Passive health checking.** NGINX open source cannot poll a backend's
`/health` endpoint. It only learns a server is bad by sending it a real client
request that fails, so the first failure after an instance dies is always paid
for by a real user. `proxy_next_upstream` hides that from the client but does
not prevent it.
*Production:* active health checks — NGINX Plus, HAProxy or a service mesh — so
an unhealthy instance leaves rotation before any client request reaches it.

**The host.** Everything runs on one machine. The most disruptive failure in
this project was not in the configuration at all: the WSL2 filesystem was
remounted read-only after an unclean shutdown, taking down Docker's own
metadata store and therefore every container at once.
*Production:* multiple hosts, orchestration that reschedules workloads, and
storage independent of any single node.

**Monitoring.** Container health is only visible to someone running
`docker compose ps`. Nothing alerts, nothing records history, and health
transitions pass unnoticed.
*Production:* export health and readiness to a monitoring system, alert on
transitions and on restart counts, and alert on the retry rate — a rising count
of comma-separated upstream entries is an early signal of an instance
degrading.

## Q7. What would you improve? How did you verify AI-assisted work?

**What I would improve**

- **Redact credentials from application logs.** The app writes its full
  connection string, password included, to stdout on every start. This defeats
  every other secrets control in the project. It needs an application code
  change, which the brief places outside scope, but it is the single most
  valuable fix remaining.
- **Make the PostgreSQL healthcheck execute a query.** `pg_isready` reported
  healthy while the database could not read a single file. `SELECT 1` would
  exercise the storage path.
- **Add image scanning to CI.** All four images are pinned by digest, which
  guarantees reproducibility and equally guarantees that a vulnerable image
  stays in use until someone deliberately updates it. Pinning without scanning
  is half of a trade.
- **Measure throughput in the failure test, not only errors.** It currently
  reports 100% availability while throughput collapses by two orders of
  magnitude.
- **Replace the Flask development server with gunicorn**, which is already in
  `requirements.txt` and unused.

**How I verified AI-assisted work**

My method was to treat every suggestion as a claim to be tested rather than an
instruction to run. When I was given a command or a prediction I asked what
mechanism was behind it, what would prove it, and what would be true instead if
it were wrong. When the answer was a prediction about the system, I wrote my own
prediction down first, so that agreeing with a suggestion could not be confused
with having reasoned about it.

That discipline caught real errors, and these are the ones that mattered:

- **A command that succeeded and printed a false answer.** I was told jq would
  skip a malformed line and continue. It does not — it aborts the whole file.
  The command exited cleanly and reported the log's last timestamp as
  11:12:49Z. There was no crash, no empty result, no warning. I caught it only
  because I had run `tail -3` on the raw file first and knew the real last line
  was 11:29:57Z, 17 minutes later. Every subsequent count would have been drawn
  from 312 of 726 lines.
- **A suggested explanation that the data disproved.** The 47 repeated
  request_ids in application.log were explained to me as NGINX retries landing
  on the second backend. Checking the records directly showed both carried the
  same `instance_id` and the access log showed a single upstream with no comma —
  so no retry had occurred. They were an error record and a request record
  about one attempt, which is a different finding entirely and changed how
  every subsequent count was taken.
- **Arithmetic that looked right and was not.** `bc` returned an error rate of
  13.00% where the correct figure is 13.19%, because `scale` truncates during
  division and the expression divided before multiplying. Two tools in the same
  analysis returned plausible wrong numbers without complaint.

Smaller corrections followed the same pattern: a `comm -3` flag that printed
633 lines when none were expected, and a predicted malformed-line number that
was off by one because a stream parser reports where it gave up rather than
where the defect is.

The general rule I ended up applying is that a tool exiting successfully is not
evidence that it processed all of its input, and a plausible answer is not
evidence that it is correct. Wherever possible I checked one measurement
against another that had been obtained a different way — line counts against
request-ID counts, error-log entries against access-log statuses, container
uptimes against the data that survived them. Where two independent counts
agreed, I recorded the number. Where they disagreed, the disagreement was the
finding.

AI use is disclosed in [AI_USAGE.md](AI_USAGE.md).
