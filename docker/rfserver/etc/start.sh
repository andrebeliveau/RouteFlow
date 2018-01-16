#!/bin/sh -e
#
# rc.local
#
# This script is executed at the end of each multiuser runlevel.
# Make sure that the script will "exit 0" on success or any other
# value on error.
#
# In order to enable or disable this script just change the execution
# bits.
#
# By default this script does nothing.
wait_port_listen() {
    port=$1
    while ! `nc -z localhost $port` ; do
        echo -n .
        sleep 1
    done
}
MONGODB_CONF=/etc/mongodb.conf
MONGODB_PORT=27017
MONGODB_ADDR=192.168.10.1
CONTROLLER_PORT=6633

#sed -i "/bind_ip/c\bind_ip = 127.0.0.1,$MONGODB_ADDR" $MONGODB_CONF
service mongod restart
wait_port_listen $MONGODB_PORT

nice -n 20 rfserver/rfserver.py rftest/rftest2config.csv &
ryu-manager --use-stderr --ofp-tcp-listen-port=$CONTROLLER_PORT ryu-rfproxy/rfproxy.py &
exit 0
