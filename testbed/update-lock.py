#!/usr/bin/env python3
"""Explicit maintainer-only dependency refresh; normal make build never runs this."""
import re
import subprocess
from pathlib import Path
root = Path(__file__).resolve().parents[1]
script = '''set -e
cat > /tmp/requirements.in
python3 -m venv /tmp/resolver
/tmp/resolver/bin/pip install -q pip==24.0 pip-tools==7.4.1 >&2
/tmp/resolver/bin/pip-compile -q --generate-hashes --allow-unsafe --strip-extras --no-emit-index-url --no-emit-trusted-host -o /tmp/requirements.lock /tmp/requirements.in >&2
cat /tmp/requirements.lock
'''
result = subprocess.run(['docker', 'run', '--rm', '-i', 'swarm-basharena-os:86082fd', 'bash', '-c', script], input=(root/'testbed/requirements.in').read_text(), capture_output=True, text=True, check=True)
lock = result.stdout
assert '--hash=sha256:' in lock
(root/'testbed/requirements.lock').write_text(lock)
blocks = re.split(r'(?m)(?=^[a-zA-Z][\w-]*==)', lock)
(root/'testbed/build-requirements.lock').write_text(''.join(b for b in blocks if b.split('==')[0].lower() in ['cython', 'setuptools', 'wheel', 'packaging']))
