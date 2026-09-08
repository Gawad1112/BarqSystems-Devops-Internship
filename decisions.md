# Technical decisions

Record at least 5 decisions. Include assumptions and limits.

## Decision
- Choice:
- Why:
- Alternative:
- Trade-off:
- Evidence / commit:
- Production improvement:

Cover your base image, health checks, networks, timeouts/retries, restart/resource settings,
storage and any other meaningful choices.

## Decision
- Choice: Changed the published container port in docker-compose.yml from 81 to 80, rather than changing nginx.conf to `listen 81`.
- Why: Both edits would have resolved the mismatch equally well. I chose the one that ends in a conventional configuration. Port 80 is the standard HTTP port and the default the nginx image expects; 81 was arbitrary and would have surprised anyone reading the config later. Fixing the side that was unusual leaves the system in a more predictable state than fixing the side that was already correct.
- Alternative: Change `listen 80;` to `listen 81;` in nginx/nginx.conf. Functionally identical.
- Trade-off: None technically. The cost of my choice is that anyone comparing my repo to the original baseline sees a change in Compose rather than in nginx.conf, so I have documented which file I changed and why.
- Evidence / commit: 66ea426. Verified before the change with `docker compose -p barq-assessment exec nginx netstat -tulpn`, which showed nginx listening only on `0.0.0.0:80` and nothing on 81.
- Production improvement: The two files agreeing on a port is something that should be enforced rather than remembered. In production I would have the validation script assert that the published container port matches the port nginx is listening on, so a future edit to one file without the other fails CI instead of failing silently at runtime.

## Decision
- Choice: Stopped the conflicting Windows service (RealPlayer Cloud Service) and set its startup type to Manual, rather than moving the project to a different host port.
- Why: The task and the video demonstration specifically require nginx on host port 8080, then a live change to 8090. Moving to a different port would have created a permanent mismatch between my documentation, my validation script and the required demonstration. The conflicting service was ordinary consumer software with no claim on that port and no dependency of mine.
- Alternative: Set `PUBLIC_PORT` in `.env` to a free port such as 8081. The README also mentions asking the organizer for a documented workstation exception if the intended ports are occupied.
- Trade-off: This fix lives on my machine, not in the repository, so it is not reproducible for anyone else and does not appear in any commit. A reviewer cannot see it in the code. I have therefore documented the exact diagnostic commands and their output in troubleshooting.md Entry 3 so the reasoning is verifiable even though the change is not.
- Evidence / commit: n/a — host machine change. Diagnosed with `netstat -ano | findstr :8080` (pid 5656), `tasklist | findstr 5656` (rpdsvc.exe), and `Get-CimInstance Win32_Service` to identify the service. Confirmed resolved when both 8080 and 8090 returned no listeners.
- Production improvement: A server would not have unrelated desktop software competing for application ports. The real lesson is that the environment should fail loudly and early: I would have the validation script check host port availability before starting the stack, so a port conflict is reported as a clear precondition failure rather than a 500-level error from the Docker daemon.

## Decision
- Choice: Treated the "only app-01 responds" symptom as a measurement problem rather than a configuration fault, and changed my test instead of the system.
- Why: Four separate hypotheses about the configuration were each disproven by direct evidence. `nginx -T` showed a valid config with both backends in the pool, the access log showed every request succeeding with status 200, and nginx itself could fetch from app-02 on demand. When the configuration is provably correct and nothing is failing, the remaining variable is the observation. `ps aux` showed eight nginx workers against a six-request sample, which is not enough to reveal a per-worker round-robin.
- Alternative: I could have changed `max_fails` and `proxy_next_upstream` at that point, since I suspected them. Had I done so and then run a larger sample, the split would have appeared and I would have wrongly concluded that those settings were the fix.
- Trade-off: Investigating rather than changing cost me time on something that turned out not to be broken. I consider that the correct trade: a fix applied to a system that was not faulty would have left me with a false belief about why it works.
- Evidence / commit: n/a — no change was made. Documented in troubleshooting.md Entry 7. Retest: 30 requests returned 16 app-01 / 14 app-02.
- Production improvement: Any check that samples probabilistic behaviour needs a sample size justified against the number of things being sampled. My validation script will send enough requests to make a per-worker round-robin visible, and will assert that both instance IDs appear, rather than assuming a small fixed count is sufficient.
