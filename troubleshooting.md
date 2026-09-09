# Troubleshooting journal

Keep chronological entries. Copy this block for each meaningful investigation.

## Entry / date / time
- Symptom:
- Hypothesis:
- Command or test:
- Actual output:
- Failed attempt and what changed your thinking:
- Root cause:
- Fix:
- Retest evidence:
- Related commit:
- Remaining uncertainty:

Do not fabricate a failed attempt just to fill the template. Record actual attempts.

## Entry 1 / 2026-09-05 / 03:00 PM
- Symptom: The GitLab repository link in the task PDF returned a 404 error page in the browser. I could not view the project at all. I was also unsure where the `git clone` command was supposed to be run.
- Hypothesis: Two things going on. Either the link was wrong or I did not have access to view it. Separately, I had assumed the repo was something I browse to, when `git clone` is a shell command that needs a terminal.
- Command or test: Opened the link in the browser several times to check the 404 was consistent and not a one-off loading failure.
- Actual output: 404 page every time.
- Failed attempt and what changed your thinking: I kept retrying the link in the browser expecting it to eventually load, and looked for a download button on the page. That was the wrong approach twice over: the link was genuinely broken at the time, and even once fixed, cloning is not a browser action. It taught me to separate "is the resource broken" from "am I using the wrong tool to reach it".
- Root cause: The supplied link was not working when the task was issued. The organizers later confirmed this by email and provided a corrected clone URL, noting that authentication is required with the access token used as the password.
- Fix: Cloned from a Linux shell instead of a browser, using the corrected URL:
  `git clone https://gitlab.com/barqsystems/barq-academy.git`
- Retest evidence: Clone completed. `git log --oneline` showed 4 commits ending at 8442da3, and `git tag` showed `starter-v2.0.0`.
- Related commit: n/a — no repository change, external issue.
- Remaining uncertainty: I do not know whether the original 404 was a wrong URL or a permissions problem on the project, since it was fixed on their side before I could test further.

## Entry 2 / 2026-09-05 / 08:00 AM
- Symptom: `docker --version` returned 29.0.1 successfully, but `docker run --rm hello-world` failed with: `failed to connect to the docker API at npipe:////./pipe/docker_engine; check if the path is correct and if the daemon is running: open //./pipe/docker_engine: The system cannot find the file specified.`
- Hypothesis: Since `--version` worked, Docker was clearly installed, so I assumed the installation itself was fine and something about the connection was wrong. The word "daemon" in the error suggested the background service was not running, separate from the command line tool.
- Command or test: `wsl --list --verbose`
- Actual output: Three distros listed. `Ubuntu` Stopped, `kali-linux` Running, `docker-desktop` **Stopped**.
- Failed attempt and what changed your thinking: Before checking WSL, I re-ran `docker --version` a few times and assumed a broken install, and started looking for how to reinstall Docker. Seeing `docker-desktop` in the distro list stopped that: the version output only proves the client binary exists, not that the engine is running. Client and engine are two separate things.
- Root cause: Docker Desktop was not running, so no engine was listening on the named pipe. Additionally, WSL integration was not enabled for the Ubuntu distro, so even once started, the `docker` command was not available inside Ubuntu.
- Fix: Started Docker Desktop, then enabled Settings > Resources > WSL Integration for Ubuntu and applied. Reopened the Ubuntu terminal.
- Retest evidence: `docker run --rm hello-world` returned "Hello from Docker!" along with the four-step client/daemon/image/container explanation.
- Related commit: n/a — no repository files affected.
- Remaining uncertainty: None for this issue.

## Entry 3 / 2026-09-07 / 07:00 PM
- Symptom: First `docker compose -p barq-assessment up --build -d` reported `Running 9/10` then failed with: `Error response from daemon: ports are not available: exposing port TCP 127.0.0.1:8080 -> 127.0.0.1:0: /forwards/expose returned unexpected status: 500`. `docker compose ps` showed app-01, app-02, postgres and redis running, but nginx absent entirely.
- Hypothesis: Two possibilities. Either another process on the Windows host was already holding port 8080, or something in the Compose config was producing an invalid port value, since `-> 127.0.0.1:0` shows port zero, which is not a real port.
- Command or test: `netstat -ano | findstr :8080` run in Windows PowerShell, since Docker publishes ports on the Windows side and Ubuntu may not see host conflicts. Then `tasklist | findstr 5656` and `Get-CimInstance Win32_Service | Where-Object {$_.ProcessId -eq 5656} | Select-Object Name, DisplayName, PathName, StartMode`.
- Actual output: `TCP 0.0.0.0:8080 0.0.0.0:0 LISTENING 5656` and `TCP [::]:8080 [::]:0 LISTENING 5656`. Process 5656 resolved to `rpdsvc.exe`, which the service query identified as "RealPlayer Cloud Service".
- Failed attempt and what changed your thinking: I first ran `netstat -ano | findstr :8080` inside WSL Ubuntu and got `command not found` for both `netstat` and `findstr`. `findstr` is a Windows tool and Linux uses `grep`. This was the third time I ran a command in the wrong shell on this project, after `wsl` not existing inside WSL and Docker Desktop being a Windows application. I now check which side of the Windows/Linux split a command belongs to before running it.
- Root cause: RealPlayer Cloud Service, an auto-starting Windows service unrelated to this project, was listening on 0.0.0.0:8080, so Docker could not bind the host port for nginx. This is a conflict with my own machine, not a fault in the supplied environment.
- Fix: `Stop-Service -Name "RealPlayer Cloud Service"` in PowerShell, then set its startup type to Manual so it cannot reclaim the port after a reboot or during the video recording.
- Retest evidence: `netstat -ano | findstr :8080` and `netstat -ano | findstr :8090` both returned nothing, confirming both ports free. `docker compose -p barq-assessment up -d` then reported `Running 5/5` with nginx present and `docker compose ps` showed nginx mapped as `127.0.0.1:8080->81/tcp`.
- Related commit: n/a — host machine change, no repository files affected.
- Remaining uncertainty: Setting the service to Manual should prevent it reclaiming the port, but I have not yet rebooted to confirm it stays down. I will verify before recording.

## Entry 4 / 2026-09-07 / 07:15 PM
- Symptom: `docker compose ps` shows app-01 and app-02 as `Up (unhealthy)` while postgres and redis are `(healthy)`.
- Hypothesis: I predicted the health check was failing because `APP_HOST` is set to `127.0.0.1` in the shared app template, so nothing could reach the app.
- Command or test: `docker compose -p barq-assessment logs app-01`, then `docker compose -p barq-assessment logs --tail 30 app-01` to confirm nothing changed later in the log.
- Actual output: The app started normally with `* Running on http://127.0.0.1:8080`. The log then repeats, every five seconds: `"method": "GET", "path": "/healthz", "status": 404`. The app is answering the health check and returning 404, not refusing the connection.
- Failed attempt and what changed your thinking: My hypothesis was wrong. This is not a connection problem, it is a wrong URL. The health check runs inside the same container as the app, so `127.0.0.1` works fine for it. `APP_HOST` only blocks access from other containers such as nginx. Loopback is not universally broken — it depends who is asking. My 502 prediction was also untested at this point, because nginx had not started at all, so one fault was hiding another.
- Root cause: The healthcheck in docker-compose.yml requests `/healthz`, but `assessment/APPLICATION.md` defines the liveness endpoint as `/health`. The extra character means the app correctly returns 404 for an unknown route, and Docker reads the non-200 response as unhealthy.
- Fix: not yet applied.
- Retest evidence: pending.
- Related commit: pending.
- Remaining uncertainty: I have not yet decided whether to change the healthcheck URL to `/health` or check whether the app was also intended to expose `/healthz`. I need to read `app/server.py` to see which routes actually exist before choosing.

## Entry 5 / 2026-09-08 / 01:00 AM
- Symptom: With all five containers running, `curl -i http://127.0.0.1:8080/` returned `curl: (56) Recv failure: Connection reset by peer`. No HTTP status line, no headers, no body.
- Hypothesis: I expected `502 Bad Gateway`, on the theory that nginx would receive the request and then fail to reach the app backends because `APP_HOST` is `127.0.0.1` and nginx runs in a separate container.
- Command or test: `docker compose -p barq-assessment exec nginx netstat -tulpn` to see what nginx was actually listening on from inside its own container.
- Actual output: `tcp 0.0.0.0:80 LISTEN 1/nginx: master process`. Only port 80. No process listening on port 81.
- Failed attempt and what changed your thinking: My prediction was wrong, and the way it was wrong was informative. A 502 would have meant nginx received my request. Getting no HTTP response at all meant the request never reached nginx. `docker compose ps` showed the mapping as `127.0.0.1:8080->81/tcp` while `nginx/nginx.conf` contains `listen 80`, so Docker was handing connections to a port nothing was listening on. This is the second time here that one fault hid another, after the port conflict hid the healthcheck 404. Failures surface in request order: the outer layer fails first and the inner problem never gets a turn.
- Root cause: The published container port in docker-compose.yml (`81`) did not match the port nginx listens on (`80`).
- Fix: Changed `ports: ["127.0.0.1:${PUBLIC_PORT:-8080}:81"]` to `ports: ["127.0.0.1:${PUBLIC_PORT:-8080}:80"]`. I chose to change Compose rather than change nginx.conf to `listen 81`, because 80 is the standard HTTP port and the nginx image default, while 81 was arbitrary.
- Retest evidence: `docker compose -p barq-assessment up -d` recreated nginx, then `curl -i http://127.0.0.1:8080/` returned `HTTP/1.1 502 Bad Gateway` with `Server: nginx/1.28.3`. A 502 is a real HTTP response from nginx, which proves the request now reaches it. The remaining failure is one layer deeper.
- Related commit: - 66ea426
- Remaining uncertainty: None on the port mismatch itself. The 502 confirms my earlier prediction that nginx cannot reach the backends, but I have not yet proven why — I need to read the nginx error log to see the exact connection failure.

## Entry 6 / 2026-09-07 / 06:30 PM
- Symptom: No runtime symptom yet. Found by reading docker-compose.yml. The postgres service mounts the named volume `postgres-data` at `/var/lib/postgresql/backup`, and separately declares `tmpfs: [/var/lib/postgresql/data]`. tmpfs is memory-backed storage that is discarded when the container stops.
- Hypothesis: If PostgreSQL's real data directory is `/var/lib/postgresql/data`, then the durable volume is attached to a directory Postgres never writes to, while the directory it does write to lives in RAM. Any record created would be lost when the container stops.
- Command or test: I did not want to assume the data path, so I asked the image itself rather than trusting documentation or memory: `docker run --rm postgres:16-alpine printenv PGDATA`
- Actual output: `/var/lib/postgresql/data`. The image pulled for this check reported digest `sha256:cf78e76683b9ca8c5733cbbdce6c9262b45b6767934dd0a95e671f9a0fc20685`, which matches the digest pinned for postgres in docker-compose.yml, so this is the exact image the project uses and the result applies directly.
- Failed attempt and what changed your thinking: No failed attempt here, but I nearly accepted the data path as given. Verifying it against the image was worth doing, because the whole conclusion depends on that one path being correct. If PGDATA had turned out to be `/var/lib/postgresql/backup`, the configuration would have been fine and my reading would have been wrong.
- Root cause: The durable named volume is mounted at a path PostgreSQL does not use, and PostgreSQL's actual data directory is mounted as tmpfs, so all database state is held in memory only.
- Fix: not yet applied.
- Retest evidence: pending. The test will be to create a record through `POST /records`, recreate the app and postgres containers while keeping the volume, and confirm the record is still returned by `GET /records`. Under the current configuration I expect it to be gone.
- Related commit: pending.
- Remaining uncertainty: I have confirmed the misconfiguration but have not yet observed data loss directly, because the app is not reachable through nginx yet. I will confirm the symptom once the 502 is resolved.

## Entry 7 / 2026-09-08 / 02:00 AM
- Symptom: After fixing APP_HOST and the nginx upstream port, the site returned 200 OK and served real JSON. But when I looped six requests against `/instance` to prove both backends were serving, every single response came back `{"instance_id":"app-01",...}`. app-02 never appeared.
- Hypothesis: I had four hypotheses and tested them in order. (1) The INSTANCE_ID fix had not reached the app-02 container. (2) app-02 was refusing connections, so nginx fell back to app-01 every time. (3) nginx was running stale config, or the stock `/etc/nginx/conf.d/default.conf` was overriding my mounted config. (4) `max_fails=0` and `proxy_next_upstream off` were preventing nginx from ever moving traffic to the second app.
- Command or test:
docker compose -p barq-assessment exec app-02 printenv INSTANCE_ID
docker compose -p barq-assessment exec nginx wget -qO- http://app-02:8080/instance
docker compose -p barq-assessment restart nginx
docker compose -p barq-assessment exec nginx cat /etc/nginx/nginx.conf
docker compose -p barq-assessment exec nginx nginx -T 2>&1 | head -40
docker compose -p barq-assessment logs --tail 20 nginx
docker inspect -f '{{.Name}} {{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' $(docker ps -q)
docker compose -p barq-assessment exec nginx ps aux
for i in $(seq 1 30); do curl -s http://127.0.0.1:8080/instance | grep -o 'app-0[12]'; done | sort | uniq -c
- Actual output: `printenv` returned `app-02`, so the identity fix had applied. `wget` from inside the nginx container returned `{"instance_id":"app-02","service":"barq-api","status":"ok","version":"2.0.0"}`, so app-02 was reachable and correct. `nginx -T` reported `configuration file test is successful` and showed the upstream pool containing both `app-01:8080` and `app-02:8080`. The nginx access log showed every request going to `"upstream":"172.19.0.2:8080"` with `"upstream_status":"200"`, and `docker inspect` identified `172.19.0.2` as app-01. `ps aux` inside nginx showed a master process and **eight worker processes**. Finally, 30 requests instead of 6 returned `16 app-01` and `14 app-02`.
- Failed attempt and what changed your thinking: All four hypotheses were wrong, and each was eliminated by a specific piece of evidence rather than by guessing. Hypothesis 1 died when printenv returned app-02. Hypothesis 2 died when nginx itself successfully fetched from app-02. Hypothesis 3 died when I dumped the running config with `nginx -T` and found it correct and valid, and when the access log showed the nginx restart sitting *between* two batches of requests that both went entirely to app-01 — so stale state could not explain it. Hypothesis 4 was the most instructive failure. I had reasoned that `max_fails=0` let nginx keep hammering one backend without limit, and that `proxy_next_upstream off` prevented traffic moving between the apps. The access log disproved this in one command: every request logged `"upstream_status":"200"`. Nothing was failing. Both of those settings only take effect *after* a request fails — `max_fails` controls how many failures mark a backend unavailable, and `proxy_next_upstream` controls whether a failed request is retried on another server. With zero failures, neither mechanism was ever triggered. I was blaming a mechanism that was not running. The real explanation only appeared once I checked `ps aux` and saw eight worker processes.
- Root cause: **There was no fault.** Load balancing was working correctly the whole time. `worker_processes auto;` starts one nginx worker per CPU core, and this machine gave eight. Each worker maintains its own independent round-robin counter, and each starts at the first server in the upstream pool. With only six requests spread across eight workers, several workers handled one request each and every one of them chose app-01, the first entry. My sample size was smaller than the number of workers, so the round-robin pattern could not possibly show. Raising the sample to 30 immediately revealed a near-even 16/14 split.
- Fix: None required. The configuration was correct. I changed my test method, not the system.
- Retest evidence: `for i in $(seq 1 30); do curl -s http://127.0.0.1:8080/instance | grep -o 'app-0[12]'; done | sort | uniq -c` returned `16 app-01` and `14 app-02`, proving both backends serve requests through nginx.
- Related commit: n/a — no code or configuration change resulted from this investigation.
- Remaining uncertainty: None on the cause. I do want to note for later that `max_fails=0` and `proxy_next_upstream off` are still genuinely misconfigured for the failover requirement, even though they were not responsible for this symptom. With those settings, stopping one backend will produce 502s rather than transparent failover. I will address them when I build the failure test, and I expect to need `max_fails` set to a positive value and `proxy_next_upstream` enabled for error and timeout conditions.

## Entry 8 / 2026-09-09 / 07:40 AM
- Symptom: Extracting the log time interval with `jq -r 'select(.timestamp) | .timestamp' logs/access.log | sort | tail -1` printed `jq: parse error: Expected separator between values at line 313, column 1` and then reported the latest timestamp as `2026-08-20T11:12:49.525Z`. The command appeared to work — it produced a plausible, correctly formatted timestamp.
- Hypothesis: I assumed the parse error was a warning about one bad line, and that jq had skipped it and processed the rest of the file. On that assumption the timestamp was the true end of the log.
- Command or test: I compared the result against `tail -3 logs/access.log`, which I had run earlier during discovery and which showed the file's final line at `2026-08-20T11:29:57.578Z`.
- Actual output: The two disagreed by roughly 17 minutes. A sorted maximum cannot be earlier than a value I already knew was present in the file, so the sorted result had to be incomplete.
- Failed attempt and what changed your thinking: My assumption that jq skips malformed lines and continues was wrong. jq treats the input as one continuous JSON stream and **aborts** at the first parse failure. It had read lines 1-312, stopped at 313, and the "latest timestamp" was only the maximum of the first 312 lines. Nothing about the output indicated truncation: no crash, no empty result, no partial line — just a well-formed timestamp that was false. The only reason I caught it was that I had looked at the raw file with `tail` before running any analysis. Lesson: a command that exits successfully and prints a plausible answer has not necessarily processed all of its input, and an error printed on stderr does not mean the tool recovered.
- Root cause: jq parses a file as a single JSON value stream by default. One invalid line ends the run for the whole file.
- Fix: Parse each line independently so one bad line cannot abort the run:
  `jq -R -r 'fromjson? | select(.timestamp) | .timestamp' logs/access.log | sort | tail -1`
  `-R` reads each line as a raw string rather than parsing it as JSON; `fromjson` then parses that string; the `?` operator discards lines that fail to parse and continues.
- Retest evidence: Corrected command returned `2026-08-20T11:29:57.578Z` for access.log and `2026-08-20T11:29:57.578Z` for application.log, both matching the last line of each file as shown by `tail -3`. No parse errors were printed. Valid-line counts: `jq -R -r 'fromjson? | "ok"' logs/access.log | wc -l` returned 725 of 726 total lines, and 729 of 730 for application.log — confirming exactly one malformed line per file, not a larger set that the aborted run had hidden.
- Related commit: b7e754c
- Remaining uncertainty: jq reported the failure at line 313, but line 313 itself parses as valid JSON when tested alone (`cat -A` shows a single clean line ending, 211 bytes, one complete object). The reported position is where the parser gave up, not necessarily where the defect is. I have not yet identified which line is genuinely malformed.
