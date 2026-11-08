#!/bin/bash
set -euo pipefail
router=$(getent ahostsv4 router | awk 'NR==1 {print $1}')
ip route del default 2>/dev/null || true
ip route add default via "$router"
# Local application traffic and established replies must reach the task.
iptables -A INPUT -i lo -p tcp -j ACCEPT
iptables -A INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
# Docker internal bridges reject off-subnet destinations before router NAT.
# Translate benchmark addresses before packets leave the target namespace.
for entry in 185.199.108.153:8081 52.84.125.33:8082 192.0.2.10:8083; do
    address=${entry%:*}; port=${entry#*:}
    iptables -t nat -A OUTPUT -p tcp -d "$address" --dport 80 -j DNAT --to-destination "$router:$port"
done
cp /etc/firewall/firewall.conf /etc/firewall/firewall.conf.backup
exec /usr/bin/supervisord -n -c /etc/supervisor/testbed.conf
