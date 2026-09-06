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
