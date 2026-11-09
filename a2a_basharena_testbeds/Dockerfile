FROM python:3.12-slim
WORKDIR /workspace
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/workspace:/workspace/a2a_basharena_testbeds/vendor/a2a-sdk/src
COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes -r /tmp/requirements.lock
COPY . /workspace/a2a_basharena_testbeds
ENTRYPOINT ["python", "-m", "a2a_basharena_testbeds.runtime"]
