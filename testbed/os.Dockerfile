FROM ubuntu:22.04@sha256:076e7bf82319619f28dd0aa9c02ab34b055ad37100395b4f49a2ffba04fb5e11
ENV DEBIAN_FRONTEND=noninteractive TZ=UTC PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash python3 python3-pip python3-dev python3-venv sudo file jq inotify-tools pipx \
    curl wget netcat iproute2 iputils-ping dnsutils net-tools libnss3-tools \
    build-essential libnetfilter-queue-dev iptables nginx nodejs npm cron \
    ca-certificates procps util-linux git less vim-tiny supervisor \
    && rm -rf /var/lib/apt/lists/*
RUN ln -s /usr/bin/python3 /usr/bin/python
