"""Runs INSIDE the grading container, next to the untrusted, model-written server.

Starts /w/server.py, waits for /health, GETs every path given on the command line, and prints
one JSON line: {"server_ok": bool, "error": str|None, "bodies": {path: [status, body]}}.
The host never executes model-written code; it only parses this output.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

PORT = os.environ["PORT"]


def get(path):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}{path}", timeout=3) as r:
            return r.status, r.read().decode(errors="replace")[:4000]
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (OSError, ValueError):  # crashed handler / dropped connection
        return 599, ""


proc = subprocess.Popen([sys.executable, "-I", "/w/server.py"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
out = {"server_ok": False, "error": None, "bodies": {}}
try:
    for _ in range(100):
        if proc.poll() is not None:
            out["error"] = proc.stderr.read().decode(errors="replace")[-300:]
            break
        try:
            if get("/health")[0] == 200:
                out["server_ok"] = True
                break
        except OSError:
            pass
        time.sleep(0.05)
    else:
        out["error"] = "no /health"
    if out["server_ok"]:
        out["bodies"] = {p: list(get(p)) for p in sys.argv[1:]}
finally:
    proc.kill()
print(json.dumps(out))
