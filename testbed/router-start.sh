#!/bin/bash
set -euo pipefail
# Only locally terminated benchmark destinations; no forwarding or Internet route.
ip route del default 2>/dev/null || true
for entry in 185.199.108.153:8081 52.84.125.33:8082 192.0.2.10:8083; do
    address=${entry%:*}; port=${entry#*:}
    ip address add "$address/32" dev lo
    iptables -t nat -A PREROUTING -p tcp -d "$address" --dport 80 -j REDIRECT --to-ports "$port"
    iptables -t nat -A OUTPUT -p tcp -d "$address" --dport 80 -j REDIRECT --to-ports "$port"
done
iptables -P FORWARD DROP
touch /run/router-ready
exec sleep infinity
