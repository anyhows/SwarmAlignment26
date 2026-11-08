FROM swarm-basharena-common:86082fd
COPY vendor/basharena/src/base_environment/logging_server/app.py /services/receiver.py
COPY vendor/basharena/src/base_environment/malware_server/app.py /services/malware.py
COPY vendor/basharena/data/tasks/10_3_all/38868061/app.py /services/database.py
COPY testbed/router-start.sh /services/router-start.sh
RUN chmod +x /services/router-start.sh
COPY testbed/tcp-proxy.py /services/tcp-proxy.py
COPY testbed/edge-start.sh /services/edge-start.sh
RUN chmod +x /services/edge-start.sh
