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
