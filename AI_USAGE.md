# AI usage disclosure

Write None if no AI was used. Otherwise record each use:

- Tool/model:
- Purpose:
- Files or decisions affected:
- What you changed or rejected:
- How you independently verified it:
- Related commit:

You may use AI and external resources. You must understand and demonstrate the work.

- Tool/model: Claude (Anthropic), used conversationally throughout the assessment.

- Purpose: I had no prior DevOps, Docker, NGINX or CI experience before starting this task, so I used it as a tutor and a second pair of eyes rather than a code generator. Concretely: explaining what containers, images, volumes, Compose networks and reverse proxies actually are; suggesting diagnostic commands when I did not know which tool to reach for; explaining error messages I had not seen before; and drafting the report entries from findings I had already produced at the terminal.

- Files or decisions affected: troubleshooting.md, decisions.md, security_review.md. Configuration changes to docker-compose.yml, nginx/nginx.conf, config/app.env, Dockerfile, .gitignore and .env.example were discussed before I made them, but I typed and applied every change myself and ran every command in my own terminal.

- What you changed or rejected: I corrected its reconstruction of my reasoning in Entry 7, where its first draft stated my hypothesis about proxy_next_upstream more cleanly than I had actually thought it. I rejected its initial claim that the app fails to log why a dependency is unavailable — a wider grep showed the app does log a dependency_error event, and the note was corrected. I also caught two of its mistakes: it suggested a psycopg2 import when the project uses psycopg 3, and it concluded from a cropped screenshot that my shell user had changed to root when it had not. Its first draft of security_review.md quoted the database password in full, which I redacted before committing.

- How you independently verified it: Every command was run by me and its real output inspected. When it told me PostgreSQL stores data in /var/lib/postgresql/data, I did not accept that and asked how it knew; I then checked it against the image itself with `docker run --rm postgres:16-alpine printenv PGDATA` and confirmed the returned digest matched the digest pinned in docker-compose.yml. I verified the resource limits had actually taken effect with `docker inspect` rather than assuming the YAML was enough. I verified the non-root change with `whoami` inside the container and confirmed the secret was gone from the image with `docker run --rm barq-assessment-app-01 cat /srv/app.env`. During the load-balancing investigation, four hypotheses were tested and all four were disproven by evidence, including one the assistant and I both found plausible; the actual cause was a sample size smaller than the nginx worker count, which only appeared after checking `ps aux` inside the container.

- Related commit: this file. The specific fixes it contributed to are listed in the evidence index and in troubleshooting.md.
