#!/bin/bash
while true; do
    if nc -z 127.0.0.1 8080; then state=UP; else state=DOWN; fi
    printf '%s %s\n' "$(date -u +%FT%TZ)" "$state" >> /var/log/socketio/monitor.log
    sleep 5
done
