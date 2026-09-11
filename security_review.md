# Security and production-readiness review

Ten findings. Each separates what is implemented in this repository from what
would be required in production. Commit hashes are given where a fix exists;
findings with no commit are either unfixed by choice or are limitations rather
than defects.

---

## Finding 1 — Database password was stored in plaintext in a tracked file

- **Risk and evidence:** `config/app.env` contained
  `DATABASE_URL=postgresql://barq_app:<redacted>@postgres:5432/barq_tasks`, and
  the file was tracked by git. `git log --all --full-history -- config/app.env`
  returns five commits, three of them from the supplied starter itself.
- **Impact:** Anyone with read access to the repository, now or at any point in
  the future, can recover the credential. Deleting a file does not remove it
  from history.
- **Implemented fix:** `e23f506` untracked the file, parameterised the password
  and expanded `.env.example`. `cc7c90e` went further and removed the
  `env_file` reference from `docker-compose.yml` entirely, sourcing
  `DATABASE_URL` and `REDIS_URL` from `.env` with `${VAR:?}` guards that fail
  loudly at parse time if unset. `config/app.env` has since been deleted from
  disk and remains in `.gitignore`.
- **Not fixed — deliberately:** the password is still recoverable from git
  history. Rewriting history would rewrite the commit trail, which is itself
  being assessed, so the correct response here is rotation rather than erasure.
- **Production follow-up:** treat any credential that has ever been committed
  as compromised and rotate it. Source credentials from a secret manager or
  from environment variables injected at deploy time, never from a file in the
  repository. Add a pre-commit secret scanner so this cannot recur.
- **How to verify:** `git ls-files config/app.env` returns nothing (untracked).
  `git log --all --full-history -- config/app.env` still returns five commits,
  demonstrating the history problem is real and unresolved.

---

## Finding 2 — The application writes its own database password to its logs

- **Risk and evidence:** on startup the app logs a `configuration_loaded`
  event containing the full connection string including the password.
  Verified on 2026-09-11:
  `docker compose -p barq-assessment logs app-01 | grep -i database_url`
  returns the credential in plaintext.
- **Impact:** this defeats every other secrets control in this review. The
  password may be absent from the image, absent from Compose and absent from
  git, but it is written to stdout on every container start, and stdout is
  collected by whatever log aggregation exists. Log readers are typically a
  much larger group than database users, and log retention routinely outlives
  credential rotation.
- **Implemented fix:** none. The fix is a change to application code, and the
  brief instructs that this is a deployment and operations exercise rather than
  an application rewrite.
- **Production follow-up:** redact credentials before logging connection
  strings. Log host, port and database name; never the password. Enforce this
  with a log filter as defence in depth, so a future code change cannot
  reintroduce it.
- **How to verify:** after a fix,
  `docker compose -p barq-assessment logs app-01 | grep -i database_url`
  should show a redacted value.

---

## Finding 3 — Database state was held in memory and lost on container stop

- **Risk and evidence:** the postgres service mounted its named volume at
  `/var/lib/postgresql/backup` while declaring
  `tmpfs: [/var/lib/postgresql/data]`. I confirmed the real data directory by
  querying the image rather than trusting documentation:
  `docker run --rm postgres:16-alpine printenv PGDATA` returned
  `/var/lib/postgresql/data`, and the pulled image digest matched the digest
  pinned in Compose.
- **Impact:** total, unrecoverable data loss on any container stop, restart or
  host reboot. It also means a backup taken from the container would have
  captured an empty directory — the backup would have appeared to succeed.
- **Implemented fix:** `1431fca` mounts the named volume at the real `PGDATA`
  and removes the tmpfs declaration. Formally retested on 2026-09-11: created a
  record through `POST /records`, ran
  `docker compose -p barq-assessment up -d --force-recreate app-01 app-02 postgres`,
  and confirmed the record survived. `docker compose ps` afterwards showed the
  three targeted containers created seconds earlier while nginx and redis
  retained their original uptime, proving they were genuinely recreated.
  Separately survived a full host reboot on 2026-09-10.
- **Production follow-up:** a volume is not a backup. It protects against
  container recreation but not against volume deletion, host failure or logical
  corruption. `backup.sh` and `restore.sh` (`3b416b6`) provide `pg_dump`-based
  logical backups, but they are run manually. Production needs scheduled
  backups stored off-host, with restores tested on a schedule rather than
  assumed to work.
- **How to verify:** documented in README and in troubleshooting.md Entry 6.

---

## Finding 4 — Containers did not restart after failure

- **Risk and evidence:** the shared app template set `restart: "no"`, so a
  container exiting for any reason stayed down until a person intervened.
- **Impact:** a single transient crash permanently removes one of two
  application instances. The system keeps serving from the survivor, so the
  failure is silent — no outage to alert on, just lost redundancy. The next
  failure is then a full outage.
- **Implemented fix:** `6e261b4` sets `restart: unless-stopped` and adds CPU
  and memory limits. Verified in practice: after a full host reboot on
  2026-09-10, `docker compose ps` showed both app containers already `Running`
  rather than `Started`, because Docker had restarted them automatically.
- **Production follow-up:** a restart policy is not monitoring. A container in
  a restart loop recovers repeatedly and silently, which hides a persistent
  fault rather than surfacing it. Restart events and health transitions should
  raise an alert.
- **How to verify:** `docker compose ps` after stopping a container with
  `docker kill`, and
  `docker inspect app-01 --format '{{.RestartCount}} {{.HostConfig.RestartPolicy.Name}}'`.

---

## Finding 5 — PostgreSQL and Redis were published to host ports

- **Risk and evidence:** the original Compose file published both datastores to
  the host, making them reachable from outside the Docker network.
- **Impact:** a database and cache exposed on the host are reachable by any
  process on that machine and, depending on the bind address and firewall, from
  the wider network. Neither has any business being reachable from outside the
  backend network; only NGINX should be publicly addressable.
- **Implemented fix:** `844ae4d` removed both port mappings. Only NGINX is
  published, and it is bound to `127.0.0.1` rather than `0.0.0.0`, so it is not
  reachable from other machines even on a trusted network.
- **Production follow-up:** enforce this rather than remember it. `validate.py`
  asserts that ports 5432, 6379, 8081 and 8082 are not reachable from the host,
  and CI runs that assertion on every push, so a regression fails the build
  instead of shipping.
- **How to verify:** `docker compose -p barq-assessment ps` shows `5432/tcp`
  and `6379/tcp` with no host binding. `python3 validate.py` asserts it
  directly.

---

## Finding 6 — The application container ran as root

- **Risk and evidence:** the Dockerfile created a dedicated `app` user and then
  set `USER root`, discarding the benefit entirely.
- **Impact:** any remote code execution in the application would run with root
  privileges inside the container. Combined with a container escape or a
  writable bind mount, that becomes a host compromise rather than an
  application compromise.
- **Implemented fix:** `4175668` removes the `USER root` line so the container
  runs as the unprivileged `app` user. Verified on 2026-09-11:
  `docker compose -p barq-assessment exec -T app-01 id` returns
  `uid=10001(app) gid=10001(app)`.
- **Production follow-up:** running as non-root is the baseline, not the
  finish. Add `read_only: true` with explicit `tmpfs` mounts for the paths that
  genuinely need writing, drop all Linux capabilities and add back only what is
  required, and set `no-new-privileges:true` so a setuid binary cannot escalate.
- **How to verify:** `docker compose -p barq-assessment exec -T app-01 id`.

---

## Finding 7 — NGINX had direct network access to PostgreSQL and Redis

- **Risk and evidence:** the nginx service was attached to both the frontend
  and backend networks, giving the internet-facing component a direct route to
  the datastores.
- **Impact:** NGINX is the only component exposed to untrusted input, which
  makes it the most likely thing to be compromised. Attaching it to the backend
  network means a compromise there reaches the database directly, rather than
  having to move through the application layer first.
- **Implemented fix:** `22fbf2e` removes nginx from the backend network. The
  backend network is additionally declared `internal: true`, so it has no route
  out to the internet at all.
- **Production follow-up:** network separation is a boundary, not a control.
  The applications still connect to PostgreSQL as a user with full rights over
  the database. A least-privilege database role limited to the tables it
  actually uses would contain a compromised application as well as a
  compromised proxy.
- **How to verify:** `validate.py` asserts both directions — that nginx
  **cannot** reach `postgres:5432` or `redis:6379`, and that app-01 **can**.
  The positive assertion matters: it proves `nc` works in the nginx image, so
  the negative results are genuine isolation rather than a missing binary
  failing for the wrong reason.

---

## Finding 8 — The PostgreSQL health check reports healthy when the database cannot serve queries

- **Risk and evidence:** found by accident on 2026-09-11. The WSL2 filesystem
  underlying Docker was remounted read-only after an unclean host shutdown.
  Throughout, `docker compose ps` reported postgres as `(healthy)` while every
  query failed. A direct connection attempt returned
  `FATAL: could not open file "base/16384/2601": Read-only file system`.
- **Impact:** the health check is `pg_isready`, which only asks whether the
  server is accepting connections. It never touches storage. A container that
  answers TCP but cannot read a single file passes this check indefinitely, so
  anything relying on container health to decide whether a dependency is usable
  is relying on a signal that does not measure usability.
- **Implemented fix:** none. The health check remains `pg_isready`.
- **Production follow-up:** the health check should execute a trivial query —
  `psql -c 'SELECT 1'` — so it exercises the storage path rather than only the
  listener. The application's own `/ready` endpoint did report the failure
  correctly, which is why it was detected at all; container health and
  application readiness should be treated as different signals, and traffic
  routing should follow readiness.
- **How to verify:** compare `docker compose ps` against
  `curl -s http://127.0.0.1:8080/ready` during a storage fault. Documented in
  troubleshooting.md.

---

## Finding 9 — No image or dependency vulnerability scanning

- **Risk and evidence:** all four images are pinned by SHA256 digest, which
  guarantees reproducibility. It also guarantees that a pinned image stays in
  use indefinitely, including after a vulnerability is published against it.
  Nothing in the repository or in CI checks for this.
- **Impact:** digest pinning converts "we might silently get a new image" into
  "we will definitely keep the old one". That is the right trade for
  reproducibility, but without scanning it means known vulnerabilities persist
  until someone happens to look.
- **Implemented fix:** none. Digest pinning was kept deliberately — see
  decisions.md — but the scanning half of that trade is missing.
- **Production follow-up:** add an image scan to CI (Trivy or Grype), failing
  the build on high and critical findings. Pair it with automated dependency
  updates so digests are advanced deliberately when a CVE lands, rather than
  drifting or staying frozen. The brief offers this as extra credit and it is
  the correct complement to pinning.
- **How to verify:** a CI step reporting scan results per image.

---

## Finding 10 — Logging is not trustworthy as evidence, and credentials are stored in plaintext by tooling

Two related weaknesses in how this system records and protects information.

- **Risk and evidence — log integrity:** the historical logs analysed in Part 1
  contain one truncated record per file, written mid-key with no value and no
  closing brace. Because a JSON stream parser consumes the following line as
  the missing value, **one truncated record makes a second valid record
  unreadable**. Separately, five byte-identical records appear in access.log at
  exact five-minute intervals, consistent with the `log collector rotated
  stream` notice — records were replayed on rotation.
- **Impact:** both defects corrupt the evidence an incident investigation
  depends on. Naive parsing of the access log silently returned results from
  only the first 312 of 726 lines, producing a plausible but wrong answer with
  no indication of truncation. Duplicated records inflate request counts. A
  monitoring system built on these logs would have reported wrong numbers
  confidently.
- **Risk and evidence — credential storage:** `git config --global
  credential.helper store` writes the GitHub token to `~/.git-credentials` in
  plaintext. Separately, a token scoped only to `repo` was refused when it
  attempted to create `.github/workflows/ci.yml`, requiring the `workflow`
  scope explicitly — least privilege working as intended, since a token that
  can modify CI can cause arbitrary code to execute with repository access.
- **Implemented fix:** none for either. The log defects are in supplied
  historical data. The credential helper is a local development convenience on
  a single-user machine with a short-lived, narrowly scoped token.
- **Production follow-up:** for logging, use a collector with at-least-once
  delivery and deduplication on a record ID, and alert on parse failure rates
  so silent truncation becomes visible. Never let a parser fail open. For
  credentials, use an OS keychain-backed helper rather than plaintext storage,
  scope tokens to the minimum required, and set short expiries.
- **How to verify:** logging — reproducible parse-exclusion counts in
  log_analysis.md Q1. Credentials — `ls -la ~/.git-credentials` shows the file
  exists on disk unencrypted.

---

## Summary

| # | Finding | Status |
|---|---|---|
| 1 | Password in a tracked file | Fixed `e23f506`, `cc7c90e`; history unfixed by choice |
| 2 | Password written to application logs | Not fixed — application code change |
| 3 | Database state on tmpfs | Fixed `1431fca`, retested |
| 4 | No restart policy or resource limits | Fixed `6e261b4`, verified after reboot |
| 5 | Datastores published to host ports | Fixed `844ae4d`, asserted in CI |
| 6 | Container ran as root | Fixed `4175668`, verified `uid=10001` |
| 7 | NGINX on the backend network | Fixed `22fbf2e`, asserted in CI |
| 8 | Health check does not detect an unusable database | Not fixed — production plan |
| 9 | No image vulnerability scanning | Not fixed — production plan |
| 10 | Log integrity and plaintext credential storage | Not fixed — production plan |

Seven findings have implemented fixes with commit references and retest
evidence. Three are production plans with no fix in this repository, stated as
such rather than presented as resolved.
