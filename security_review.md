# Security and production-readiness review

Record at least 8 concrete risks or improvements relevant to your final solution.
This is a review requirement, not the number of hidden faults.

For each finding:
- Risk and evidence:
- Impact:
- Implemented fix / commit:
- Production follow-up:
- How to verify:

Cover secrets, ports, container user, image selection, networks, persistence/backup,
logging/monitoring and availability. Separate completed work from planned improvements.

## Finding 1 — Database password stored in plaintext inside the repository
- Risk and evidence: `config/app.env` contains `DATABASE_URL=postgresql://barq_app:<redacted>@postgres:5433/barq_tasks`. The credential is in a file inside the project directory, loaded into both app containers via `env_file`.
- Impact: If this file is tracked by git, the password is in the repository history and remains recoverable even after deletion. Anyone with read access to the repo, now or later, has the database credential.
- Implemented fix / commit: Not yet fixed. Verification of whether it is tracked is pending (`git ls-files config/app.env`).
- Production follow-up: Credentials should come from a secret manager or from environment variables injected at deploy time, never from a file in the repo. The repo should contain only `.env.example` with placeholder values. If a real credential has ever been committed, it must be rotated, not just removed, because removal does not erase history.
- How to verify: `git ls-files config/app.env` to confirm tracking status, and `git log --all --full-history -- config/app.env` to check whether it appears in history.

## Finding 2 — Application password is written into the application's own logs
- Risk and evidence: On startup, app-01 logs `"database_url": "postgresql://barq_app:<redacted>@postgres:5433/barq_tasks"` as part of its `configuration_loaded` event, visible in `docker compose logs app-01`.
- Impact: Credentials leak into any system that collects container logs. Log aggregators are typically read by more people than have database access, and log retention often outlives credential rotation.
- Implemented fix / commit: Not yet fixed.
- Production follow-up: Redact credentials before logging connection strings. Log the host, port and database name, never the password. This is a code change in the application's startup logging.
- How to verify: `docker compose -p barq-assessment logs app-01 | grep -i database_url` should show a redacted value.

## Finding 3 — Database state is held in memory and lost on container stop
- Risk and evidence: The postgres service mounts its named volume at `/var/lib/postgresql/backup` while declaring `tmpfs: [/var/lib/postgresql/data]`. I confirmed the real data directory by querying the image directly: `docker run --rm postgres:16-alpine printenv PGDATA` returned `/var/lib/postgresql/data`. The pulled image digest matched the digest pinned in Compose.
- Impact: Total data loss on any container stop, restart or host reboot. There is no durable copy, so this is unrecoverable rather than merely inconvenient. It also means backups taken from the container would capture an empty directory.
- Implemented fix / commit: Not yet fixed.
- Production follow-up: Mount the named volume at the actual `PGDATA` path and remove the tmpfs declaration. Beyond that, a volume alone is not a backup — it protects against container recreation but not against volume deletion, host failure or logical corruption. Scheduled `pg_dump` backups stored off-host are required, with restores tested regularly rather than assumed.
- How to verify: Create a record through `POST /records`, recreate the app and postgres containers while keeping the volume, and confirm `GET /records` still returns it.

## Finding 4 — Containers do not restart after failure
- Risk and evidence: The shared app template sets `restart: "no"`, so a container that exits for any reason stays down until a person intervenes.
- Impact: A single transient crash permanently removes one of the two application instances. The system continues serving from the survivor, which means the failure is silent — there is no outage to alert on, just reduced capacity and no redundancy left. The next failure is then a full outage.
- Implemented fix / commit: Not yet fixed.
- Production follow-up: Set `restart: unless-stopped` so containers recover automatically. Restart policies are not a substitute for monitoring, though — a container in a restart loop needs to raise an alert, otherwise automatic recovery just hides a persistent fault.
- How to verify: Stop one app container and confirm it comes back on its own, then confirm the event is visible somewhere other than by manually running `docker compose ps`.
