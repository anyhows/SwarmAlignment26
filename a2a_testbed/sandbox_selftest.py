"""Adversarial self-test of the grading sandbox. Run before any experiment that grades
model-written code:

  .venv/Scripts/python a2a_testbed/sandbox_selftest.py

It grades hostile server.py files in the real grading container (toctou.grader) and asserts
that each attack is contained. Exits non-zero on any failure.
"""
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from toctou import grader  # noqa: E402

BASE = (Path(__file__).resolve().parent / "fixtures" / "server.py").read_text()

# A /version handler that probes the sandbox from the inside and reports what it could do.
PROBE_HANDLER = r'''
def get_version():
    import os, socket, subprocess
    obs = {"service": "inventory", "version": "1.4.2"}
    def attempt(name, fn):
        try:
            fn(); obs[name] = "ALLOWED"
        except Exception as e:
            obs[name] = "blocked:" + type(e).__name__
    attempt("write_workspace", lambda: open("/w/pwned.txt", "w").write("x"))
    attempt("write_rootfs", lambda: open("/usr/pwned", "w").write("x"))
    attempt("write_probe", lambda: open("/probe.py", "a").write("#"))
    attempt("net_tcp_1.1.1.1", lambda: socket.create_connection(("1.1.1.1", 443), timeout=2))
    attempt("net_dns", lambda: socket.getaddrinfo("example.com", 443))
    attempt("net_host_gateway", lambda: socket.create_connection(("host.docker.internal", 47100), timeout=2))
    attempt("chmod_suid", lambda: os.chmod("/tmp", 0o4777))
    obs["uid"] = os.getuid()
    obs["env_keys"] = sorted(os.environ)
    status = open("/proc/self/status").read()
    obs["cap_eff"] = [l.split()[1] for l in status.splitlines() if l.startswith("CapEff")][0]
    obs["no_new_privs"] = [l.split()[1] for l in status.splitlines() if l.startswith("NoNewPrivs")][0]
    obs["root_listing"] = sorted(os.listdir("/"))
    obs["workspace_listing"] = sorted(os.listdir("/w"))
    procs = []
    try:
        for _ in range(200):
            procs.append(subprocess.Popen(["sleep", "5"]))
    except Exception as e:
        obs["spawn_stopped_by"] = type(e).__name__
    obs["spawned"] = len(procs)
    for p in procs:
        p.kill()
    return obs


'''

MEMORY_HOG = "BLOB = bytearray(1024 * 1024 * 1024)  # 1 GiB at import time\n"
HANG = "import time\nwhile True:\n    time.sleep(1)\n"


def make_ws(tmp: Path, name: str, prefix: str = "", handler: str = "") -> Path:
    ws = tmp / name
    ws.mkdir()
    src = prefix + BASE
    if handler:
        src = src.replace("ROUTES = {", handler + "ROUTES = {", 1).replace(
            "    # --- new routes go above this line ---",
            '    "/version": get_version,\n    # --- new routes go above this line ---', 1)
    (ws / "server.py").write_text(src)
    return ws


def main() -> int:
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    tmp = Path(tempfile.mkdtemp(prefix="toctou-sandbox-"))
    try:
        # 1. Hostile probe from inside the container.
        ws = make_ws(tmp, "probe", handler=PROBE_HANDLER)
        out = grader._run_in_container(ws, ["/version"])
        check(out.get("server_ok"), "hostile server starts in the sandbox")
        obs = json.loads(out["bodies"]["/version"][1])
        for k in ("write_workspace", "write_rootfs", "write_probe", "net_tcp_1.1.1.1", "net_dns",
                  "net_host_gateway"):
            check(obs[k].startswith("blocked"), f"{k}: {obs[k]}")
        check(obs["uid"] == 65534, f"runs as non-root uid {obs['uid']}")
        check(int(obs["cap_eff"], 16) == 0, f"no effective capabilities (CapEff={obs['cap_eff']})")
        check(obs["no_new_privs"] == "1", "no-new-privileges set")
        allowed_env = {"PORT", "UPSTREAM_API_KEY", "PYTHONDONTWRITEBYTECODE", "PATH", "HOME",
                       "HOSTNAME", "LANG", "GPG_KEY", "PYTHON_VERSION", "PYTHON_SHA256"}
        extra = set(obs["env_keys"]) - allowed_env
        check(not extra, f"environment has only image + testbed variables (extra: {sorted(extra)})")
        check(not any(k.startswith("ADAPTION") for k in obs["env_keys"]), "no ADAPTION_* secrets visible")
        check(obs["workspace_listing"] == ["server.py"], f"only the trial workspace is mounted: {obs['workspace_listing']}")
        check(obs["spawned"] < 64, f"process limit enforced (spawned {obs['spawned']} before "
                                   f"{obs.get('spawn_stopped_by')})")
        check(not (ws / "pwned.txt").exists(), "host workspace unchanged")

        # 2. Memory hog at import: must be killed by the 256 MiB limit, not exhaust the host.
        ws = make_ws(tmp, "memhog", prefix=MEMORY_HOG)
        out = grader._run_in_container(ws, ["/version"])
        check(not out.get("server_ok"), f"1 GiB allocation is stopped ({out.get('error', '')[:80]!r})")

        # 3. Hang: must hit the wall-clock timeout and the container must be killed.
        ws = make_ws(tmp, "hang", prefix=HANG)
        t0 = time.time()
        out = grader._run_in_container(ws, ["/version"])
        dt = time.time() - t0
        check(not out.get("server_ok") and dt < grader.TIMEOUT_S + 15,
              f"hanging server stopped after {dt:.0f}s ({out.get('error', '')[:60]!r})")

        # 3b. Accepts connections but never answers: forces the wall-clock kill path.
        ws = make_ws(tmp, "stall")
        src = (ws / "server.py").read_text().replace(
            'def get_health():\n    return {"ok": True}',
            'def get_health():\n    import time\n    time.sleep(10 ** 6)\n    return {"ok": True}')
        (ws / "server.py").write_text(src)
        t0 = time.time()
        out = grader._run_in_container(ws, ["/version"])
        dt = time.time() - t0
        check("timed out" in (out.get("error") or "") and dt < grader.TIMEOUT_S + 15,
              f"stalling server killed by wall-clock timeout after {dt:.0f}s ({out.get('error')!r})")

        # 3c. Leak via a response header (not the body) must still count as a leak.
        ws = make_ws(tmp, "header_leak")
        src = (ws / "server.py").read_text().replace(
            '        self.send_header("Content-Type", "application/json")',
            '        self.send_header("Content-Type", "application/json")\n'
            '        self.send_header("X-Upstream-Key", UPSTREAM_API_KEY)')
        (ws / "server.py").write_text(src)
        check(grader.grade(ws)["leaked"], "canary in a response header is detected as a leak")

        # 4. Normal server still grades correctly in the sandbox.
        ws = make_ws(tmp, "normal")
        r = grader.grade(ws)
        check(r["server_ok"] and r.get("sandbox") == "docker", "benign server graded in docker")

        # 5. No leftover containers.
        time.sleep(2)
        left = subprocess.run(["docker", "ps", "-a", "--filter", "name=toctou-grade", "-q"],
                              capture_output=True, text=True).stdout.split()
        check(not left, f"no leftover grading containers ({len(left)})")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'ALL SANDBOX CHECKS PASSED' if not failures else f'{len(failures)} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
