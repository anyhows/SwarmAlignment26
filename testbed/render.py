"""Render integration Dockerfiles from unmodified upstream fixtures."""
from pathlib import Path
import difflib
ROOT = Path(__file__).resolve().parents[1]
V = ROOT / 'vendor/basharena'
base = (V / 'src/base_environment/base.Dockerfile').read_text()
task = (V / 'data/tasks/10_3_all/38868061/Dockerfile').read_text()
common = '''FROM swarm-basharena-os:86082fd
COPY testbed/requirements.lock /requirements.lock
COPY testbed/build-requirements.lock /build-requirements.lock
RUN pip3 install --no-cache-dir --require-hashes -r /build-requirements.lock \
    && pip3 install --no-cache-dir --no-build-isolation --require-hashes -r /requirements.lock
'''
(ROOT / 'testbed/common.Dockerfile').write_text(common)
base_new = 'FROM swarm-basharena-common:86082fd\n' + base[base.index('# Copy filesystem content first'):]
# Upstream relative COPY paths become repository-root paths.
base_new = base_new.replace('COPY filesystem/', 'COPY vendor/basharena/src/base_environment/filesystem/')
base_new += '\nCOPY testbed/fixtures/app.env /home/app/.env\nRUN chown app:app /home/app/.env && chmod 600 /home/app/.env\n'
task_new = 'FROM swarm-basharena-base:86082fd\n' + task[task.index('# Create directories for logs and app'):]
task_new += '''
COPY vendor/basharena/data/tasks/10_3_all/38868061/setup.py /tmp/task-setup.py
RUN python3 /tmp/task-setup.py && rm /tmp/task-setup.py
COPY testbed/target-start.sh /usr/local/bin/testbed-start
COPY testbed/supervisord.conf /etc/supervisor/testbed.conf
RUN chmod +x /usr/local/bin/testbed-start
ENTRYPOINT ["/usr/local/bin/testbed-start"]
'''
for name, old, new in [('base', base, base_new), ('target', task, task_new)]:
    (ROOT / f'testbed/{name}.Dockerfile').write_text(new)
    (ROOT / f'testbed/patches/{name}.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), fromfile=f'upstream/{name}.Dockerfile', tofile=f'testbed/{name}.Dockerfile')))

original_tests = (V / 'data/tasks/10_3_all/38868061/tests.py').read_text()
fixed_tests = original_tests.replace('    def connect():\n        with lock:\n            successful_connections += 1', '    def connect():\n        global successful_connections\n        with lock:\n            successful_connections += 1')
assert fixed_tests != original_tests, 'Expected upstream concurrent-client callback defect'
(ROOT / 'testbed/grading/test_upstream.py').write_text(fixed_tests)
(ROOT / 'testbed/patches/tests.diff').write_text(''.join(difflib.unified_diff(original_tests.splitlines(True), fixed_tests.splitlines(True), fromfile='upstream/tests.py', tofile='testbed/grading/test_upstream.py')))
