#!/bin/bash
set -euo pipefail
target=$(getent ahostsv4 target | awk 'NR==1 {print $1}')
# Publishing requires a non-internal Docker interface on this Docker version.
# It is a trusted ingress relay, with no default route and no Internet egress.
ip route del default 2>/dev/null || true
iptables -P FORWARD DROP
iptables -A OUTPUT -o lo -j ACCEPT
iptables -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
iptables -A OUTPUT -d "$target" -p tcp --dport 80 -j ACCEPT
iptables -P OUTPUT DROP
exec setpriv --reuid=nobody --regid=nogroup --init-groups --bounding-set=-all --no-new-privs python3 /services/tcp-proxy.py
