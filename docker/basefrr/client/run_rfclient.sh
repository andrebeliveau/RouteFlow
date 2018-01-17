#!/bin/sh
sleep 3
/etc/init.d/frr start
/rfclient 2>&1 >/var/log/rfclient.log

