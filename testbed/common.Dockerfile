FROM swarm-basharena-os:86082fd
COPY testbed/requirements.lock /requirements.lock
COPY testbed/build-requirements.lock /build-requirements.lock
RUN pip3 install --no-cache-dir --require-hashes -r /build-requirements.lock     && pip3 install --no-cache-dir --no-build-isolation --require-hashes -r /requirements.lock
