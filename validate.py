#!/usr/bin/env python3
"""
validate.py — environment validation for the BARQ DevOps assessment.

Checks public access, every endpoint in the application contract, both
backends, PostgreSQL and Redis readiness, network isolation and prohibited
host ports.

Exits 0 if every check passes, 1 if any check fails.
Standard library only — no pip install required, so CI runs it unchanged.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT = "barq-assessment"


def read_public_port(default=8080):
    """
    Read PUBLIC_PORT from .env, falling back to the Compose default.

    The published port is configuration, not a constant, so the validator
    reads the same source Compose does. This means the script follows the
    stack when the public port changes, rather than needing to be edited —
    a validator you have to modify to make it pass is not a validator.

    os.environ takes precedence so the port can be overridden for a one-off
    run without editing any file.
    """
    if "PUBLIC_PORT" in os.environ:
        return int(os.environ["PUBLIC_PORT"])
    try:
        with open(".env") as f:
            for line in f:
                line = line.strip()
                # Skip blank lines and comments.
                if not line or line.startswith("#"):
                    continue
                key, _, value = line.partition("=")
                if key.strip() == "PUBLIC_PORT":
                    return int(value.strip())
    except FileNotFoundError:
        pass
    return default


PUBLIC_PORT = read_public_port()
BASE_URL = f"http://127.0.0.1:{PUBLIC_PORT}"

# Ports that must NOT be reachable from the host. The datastores and the app
# instances are never published. The alternate public port is included too:
# whichever of 8080/8090 is not currently in use must be closed, which proves
# a port change actually moved the listener rather than adding a second one.
PROHIBITED_PORTS = [5432, 6379, 8081, 8082]
ALTERNATE_PUBLIC_PORT = 8090 if PUBLIC_PORT == 8080 else 8080
PROHIBITED_PORTS.append(ALTERNATE_PUBLIC_PORT)

BALANCE_SAMPLE = 50

READY_TIMEOUT_SECONDS = 60
READY_POLL_SECONDS = 2

REQUEST_TIMEOUT = 10


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

failures = []


def report(name, passed, detail=""):
    """Print one PASS/FAIL line and record failures for the exit code."""
    status = "PASS" if passed else "FAIL"
    line = f"[{status}] {name}"
    if detail:
        line += f" — {detail}"
    print(line, flush=True)
    if not passed:
        failures.append(name)
    return passed


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def http(path, method="GET", body=None):
    """
    Make one HTTP request and return (status, headers, parsed_json).

    Returns status 0 on a connection-level failure, so callers can tell the
    difference between "the server said no" and "nothing answered".
    urllib raises HTTPError for 4xx/5xx, which we catch and treat as a normal
    response — a 404 is a valid answer, not an exception, for our purposes.
    """
    url = BASE_URL + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            raw = resp.read().decode()
            return resp.status, dict(resp.headers), safe_json(raw)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        return e.code, dict(e.headers), safe_json(raw)
    except Exception as e:
        return 0, {}, {"_error": str(e)}


def safe_json(raw):
    """Parse JSON, returning the raw text under a key if it is not JSON."""
    try:
        return json.loads(raw)
    except Exception:
        return {"_raw": raw}


# ---------------------------------------------------------------------------
# Bounded wait for readiness
# ---------------------------------------------------------------------------

def wait_for_ready():
    """
    Poll /ready until it returns 200, or until the timeout expires.

    This is the bounded wait the task requires. Every other check assumes the
    stack is up, so this runs first and fails fast if it never becomes ready.
    """
    deadline = time.time() + READY_TIMEOUT_SECONDS
    last = None
    while time.time() < deadline:
        status, _, payload = http("/ready")
        if status == 200:
            waited = READY_TIMEOUT_SECONDS - int(deadline - time.time())
            return report("stack becomes ready", True, f"after ~{waited}s")
        last = f"status={status} body={payload}"
        time.sleep(READY_POLL_SECONDS)
    return report("stack becomes ready", False,
                  f"not ready within {READY_TIMEOUT_SECONDS}s; last: {last}")


# ---------------------------------------------------------------------------
# Endpoint checks — against assessment/APPLICATION.md
# ---------------------------------------------------------------------------

def check_root():
    status, _, body = http("/")
    ok = status == 200 and "message" in body and "instance_id" in body
    report("GET / returns 200 with message and instance_id",
           ok, f"status={status}")


def check_health():
    """Liveness. Must be 200 and must NOT depend on postgres or redis."""
    status, _, body = http("/health")
    ok = status == 200 and body.get("status") == "alive"
    report("GET /health returns 200 alive", ok, f"status={status}")


def check_ready():
    """
    Readiness. Must be 200 AND both dependencies must report ready.

    Checking only the status code would not be enough: the point of /ready is
    the dependency detail, and a 200 with a degraded dependency would be a
    silent pass.
    """
    status, _, body = http("/ready")
    deps = body.get("dependencies", {})
    ok = (status == 200
          and body.get("status") == "ready"
          and deps.get("postgres") == "ready"
          and deps.get("redis") == "ready")
    report("GET /ready returns 200 with postgres and redis ready",
           ok, f"status={status} deps={deps}")


def check_instance_header():
    """The contract requires the identity in the X-Instance-ID header."""
    status, headers, body = http("/instance")
    header_id = headers.get("X-Instance-ID")
    ok = status == 200 and header_id and header_id == body.get("instance_id")
    report("GET /instance returns X-Instance-ID matching the body",
           ok, f"status={status} header={header_id}")


def check_counter():
    """
    Redis-backed counter. Two calls must return strictly increasing values.

    A single call proves nothing — a hardcoded constant would pass. Requiring
    an increase proves a real Redis write happened between the two calls.
    """
    s1, _, b1 = http("/counter")
    s2, _, b2 = http("/counter")
    v1, v2 = b1.get("counter"), b2.get("counter")
    ok = (s1 == 200 and s2 == 200
          and isinstance(v1, int) and isinstance(v2, int)
          and v2 > v1)
    report("GET /counter increments via Redis", ok, f"{v1} -> {v2}")


def check_records_create_and_list():
    """
    POST then GET. The created record must appear in the subsequent list —
    proving a real database write, not an echo of the request.
    """
    title = f"validate-{int(time.time())}"
    status, _, created = http("/records", method="POST", body={"title": title})
    created_ok = status == 201 and created.get("record", {}).get("title") == title
    report("POST /records returns 201 and the created record",
           created_ok, f"status={status}")

    status, _, listed = http("/records")
    titles = [r.get("title") for r in listed.get("records", [])]
    ok = status == 200 and title in titles
    report("GET /records lists the record just created",
           ok, f"status={status} count={len(titles)}")


def check_invalid_title_rejected():
    """
    The contract says invalid titles return 400. Validating only the happy
    path would miss an app that accepts anything.
    """
    status, _, body = http("/records", method="POST", body={"title": ""})
    ok = status == 400
    report("POST /records rejects an empty title with 400",
           ok, f"status={status} error={body.get('error')}")


def check_unknown_route():
    status, _, _ = http("/definitely-not-a-real-route")
    ok = status == 404
    report("unknown route returns 404", ok, f"status={status}")


# ---------------------------------------------------------------------------
# Both backends serve traffic
# ---------------------------------------------------------------------------

def check_both_backends():
    """
    Send BALANCE_SAMPLE requests and require at least two distinct instance
    IDs. See the comment on BALANCE_SAMPLE for why the sample must be large.
    """
    seen = {}
    for _ in range(BALANCE_SAMPLE):
        status, headers, _ = http("/instance")
        if status == 200:
            iid = headers.get("X-Instance-ID")
            if iid:
                seen[iid] = seen.get(iid, 0) + 1
    ok = len(seen) >= 2
    detail = ", ".join(f"{k}={v}" for k, v in sorted(seen.items()))
    report(f"both backends serve traffic ({BALANCE_SAMPLE} requests)",
           ok, detail or "no instance IDs seen")


# ---------------------------------------------------------------------------
# Host port checks
# ---------------------------------------------------------------------------

def port_open(host, port, timeout=2):
    """Return True if a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def check_public_port():
    ok = port_open("127.0.0.1", PUBLIC_PORT)
    report(f"NGINX is reachable on host port {PUBLIC_PORT}", ok,
           "read from .env" if PUBLIC_PORT != 8080 else "")

def check_prohibited_ports():
    """
    Only NGINX may be published. PostgreSQL, Redis and the app instances must
    not be reachable from the host.
    """
    for port in PROHIBITED_PORTS:
        ok = not port_open("127.0.0.1", port)
        report(f"host port {port} is not published", ok,
               "" if ok else "port is reachable from the host")


# ---------------------------------------------------------------------------
# Network isolation
# ---------------------------------------------------------------------------

def docker_exec(container, args):
    """Run a command inside a container. Returns (returncode, output)."""
    cmd = ["docker", "compose", "-p", PROJECT, "exec", "-T", container] + args
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        return r.returncode, (r.stdout + r.stderr).strip()
    except Exception as e:
        return 1, str(e)


def check_nginx_cannot_reach_datastores():
    """
    NGINX is on the frontend network only. It must not be able to open a
    connection to PostgreSQL or Redis.

    Note this asserts a NEGATIVE — we need the connection to fail. A check
    that can only pass is not a check, so a failure here means the network
    separation has been lost.
    """
    for host, port in [("postgres", 5432), ("redis", 6379)]:
        rc, out = docker_exec("nginx", ["nc", "-z", "-w", "2", host, str(port)])
        ok = rc != 0
        report(f"nginx cannot reach {host}:{port}", ok,
               "" if ok else "connection succeeded — networks are not isolated")


def check_apps_can_reach_datastores():
    """
    The mirror of the check above. The apps ARE on the backend network and
    must be able to reach both datastores by service name, not by container IP.
    """
    for host, port in [("postgres", 5432), ("redis", 6379)]:
        code = (f"import socket;socket.create_connection(('{host}',{port}),"
                f"timeout=3);print('ok')")
        rc, out = docker_exec("app-01", ["python", "-c", code])
        ok = rc == 0 and "ok" in out
        report(f"app-01 can reach {host}:{port} by service name", ok,
               "" if ok else out[:120])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print(f"BARQ environment validation — public port {PUBLIC_PORT}")
    print("=" * 60)

    if not wait_for_ready():
        print("\nStack never became ready — skipping remaining checks.")
        print(f"\nRESULT: FAIL ({len(failures)} failed)")
        return 1

    print("\n-- endpoints --")
    check_root()
    check_health()
    check_ready()
    check_instance_header()
    check_counter()
    check_records_create_and_list()
    check_invalid_title_rejected()
    check_unknown_route()

    print("\n-- load balancing --")
    check_both_backends()

    print("\n-- host ports --")
    check_public_port()
    check_prohibited_ports()

    print("\n-- network isolation --")
    check_nginx_cannot_reach_datastores()
    check_apps_can_reach_datastores()

    print("\n" + "=" * 60)
    if failures:
        print(f"RESULT: FAIL ({len(failures)} of the checks above failed)")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("RESULT: PASS (all checks passed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
