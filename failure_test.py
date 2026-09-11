#!/usr/bin/env python3
"""
failure_test.py — prove the stack survives losing one backend.

Stops one application instance, drives traffic for a fixed duration while it
is down, restores it, and proves the recovered instance serves requests again.

Exits 0 if the system behaved acceptably, 1 if not.
Standard library only, so CI runs it unchanged.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "http://127.0.0.1:8080"
PROJECT = "barq-assessment"
TARGET = "app-02"          # the instance this test stops

# Measurement window: drive traffic for a fixed DURATION rather than a fixed
# count, so the result is expressed as an availability figure over time.
OUTAGE_DURATION = 15       # seconds of traffic while the backend is down
BASELINE_DURATION = 5      # seconds of traffic before stopping anything

# Tolerance: max_fails=3 means up to 3 requests can reach the dead backend
# before NGINX benches it. proxy_next_upstream should rescue them, but one
# observed retry took 2.005s at proxy_connect_timeout, so a slower machine
# may behave differently. See decisions.md.
MAX_ALLOWED_ERRORS = 3

# Must exceed nginx's worst case (connect 2s + read 4s), so our own
# impatience is never recorded as a system failure.
REQUEST_TIMEOUT = 10

# Recovery wait: fail_timeout=10s before a benched backend is retried, plus
# the 5s healthcheck interval.
RECOVERY_WAIT = 15
RECOVERY_SAMPLE = 50       # requests used to prove both backends serve again

failures = []


def report(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line, flush=True)
    if not passed:
        failures.append(name)
    return passed


def http(path):
    """Return (status_code, instance_id). Status 0 means nothing answered."""
    try:
        req = urllib.request.Request(BASE_URL + path)
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as r:
            r.read()
            return r.status, r.headers.get("X-Instance-ID")
    except urllib.error.HTTPError as e:
        e.read()
        return e.code, e.headers.get("X-Instance-ID")
    except Exception:
        return 0, None


def drive_traffic(seconds, label):
    """
    Send requests as fast as they complete, for a fixed number of seconds.

    Returns a dict of counts. Measuring by DURATION rather than by request
    count means the result can be stated as availability over a time window,
    which is how an outage is actually described.
    """
    counts = {"total": 0, "ok": 0, "errors": 0}
    by_status = {}
    by_instance = {}

    deadline = time.time() + seconds
    while time.time() < deadline:
        status, iid = http("/")
        counts["total"] += 1
        by_status[status] = by_status.get(status, 0) + 1
        if status == 200:
            counts["ok"] += 1
            if iid:
                by_instance[iid] = by_instance.get(iid, 0) + 1
        else:
            counts["errors"] += 1

    counts["by_status"] = by_status
    counts["by_instance"] = by_instance
    counts["rate"] = round(counts["total"] / seconds, 1)

    print(f"    {label}: {counts['total']} requests in {seconds}s "
          f"({counts['rate']}/s), {counts['ok']} ok, {counts['errors']} errors")
    print(f"    statuses: {by_status}")
    print(f"    instances: {by_instance}")
    return counts


def compose(*args):
    """Run a docker compose command for this project."""
    cmd = ["docker", "compose", "-p", PROJECT] + list(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return r.returncode, (r.stdout + r.stderr).strip()


def main():
    print("=" * 60)
    print(f"BARQ failure test — stopping {TARGET}")
    print("=" * 60)

    # --- Baseline -----------------------------------------------------------
    # Establish that BOTH backends are serving before we break anything.
    # Without this, a test that "passes" during the outage proves nothing —
    # the target might already have been down.
    print("\n-- baseline (both backends up) --")
    base = drive_traffic(BASELINE_DURATION, "baseline")
    report("baseline: no errors with both backends up",
           base["errors"] == 0, f"{base['errors']} errors")
    report("baseline: both backends serving",
           len(base["by_instance"]) >= 2, str(base["by_instance"]))

    # --- Stop one backend ---------------------------------------------------
    # 'stop' sends SIGTERM and leaves the container in place so it can be
    # started again. 'down' would remove it entirely.
    print(f"\n-- stopping {TARGET} --")
    rc, out = compose("stop", TARGET)
    if not report(f"{TARGET} stopped", rc == 0, out[:120]):
        return 1

    # --- Traffic during the outage -----------------------------------------
    print(f"\n-- outage ({OUTAGE_DURATION}s of traffic, {TARGET} down) --")
    outage = drive_traffic(OUTAGE_DURATION, "outage")

    availability = round(100 * outage["ok"] / outage["total"], 2) if outage["total"] else 0

    report(f"service stayed available during the outage "
           f"(<= {MAX_ALLOWED_ERRORS} errors allowed)",
           outage["errors"] <= MAX_ALLOWED_ERRORS,
           f"{outage['errors']} errors of {outage['total']} requests, "
           f"{availability}% available")

    # Every successful request must have been served by the SURVIVOR.
    # If the stopped instance appears here, it did not actually stop.
    served_by_target = outage["by_instance"].get(TARGET, 0)
    report(f"no traffic served by the stopped {TARGET}",
           served_by_target == 0, f"{served_by_target} requests")

    report("the surviving backend served traffic",
           outage["ok"] > 0, f"{outage['ok']} successful requests")

    # --- Restore ------------------------------------------------------------
    print(f"\n-- restoring {TARGET} --")
    rc, out = compose("start", TARGET)
    if not report(f"{TARGET} started", rc == 0, out[:120]):
        return 1

    # fail_timeout=10s must elapse before NGINX retries a benched backend,
    # and the healthcheck runs every 5s. Waiting less than this would test
    # our patience rather than the system's recovery.
    print(f"    waiting {RECOVERY_WAIT}s for recovery "
          f"(fail_timeout 10s + healthcheck interval 5s)")
    time.sleep(RECOVERY_WAIT)

    # --- Prove recovery -----------------------------------------------------
    # 50 requests, for the same reason validate.py uses 50: nginx runs one
    # worker per core, each with its own round-robin counter, so a small
    # sample can show a single backend even when both are serving.
    print("\n-- recovery --")
    seen = {}
    errors = 0
    for _ in range(RECOVERY_SAMPLE):
        status, iid = http("/instance")
        if status == 200 and iid:
            seen[iid] = seen.get(iid, 0) + 1
        else:
            errors += 1

    report(f"no errors after recovery ({RECOVERY_SAMPLE} requests)",
           errors == 0, f"{errors} errors")
    report(f"the recovered {TARGET} is serving requests again",
           seen.get(TARGET, 0) > 0, str(seen))
    report("both backends serving after recovery",
           len(seen) >= 2, str(seen))

    # --- Summary ------------------------------------------------------------
    print("\n" + "=" * 60)
    print("MEASUREMENTS")
    print(f"  baseline:  {base['total']} requests, {base['errors']} errors")
    print(f"  outage:    {outage['total']} requests over {OUTAGE_DURATION}s "
          f"({outage['rate']}/s), {outage['errors']} errors, "
          f"{availability}% available")
    print(f"  recovery:  {RECOVERY_SAMPLE} requests, {errors} errors, {seen}")
    print("=" * 60)

    if failures:
        print(f"RESULT: FAIL ({len(failures)} checks failed)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
