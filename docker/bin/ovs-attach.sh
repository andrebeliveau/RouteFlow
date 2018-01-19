#!/bin/sh
ovs-vsctl del-br dp0
ovs-vsctl add-br dp0
ovs-docker add-port dp0 frra1 frra  --ipaddress=172.31.1.1 --macaddress=02:a1:a1:a1:a1:a1
ovs-docker add-port dp0 frrb1 frrb  --ipaddress=172.31.2.1 --macaddress=02:b1:b1:b1:b1:b1
ovs-docker add-port dp0 frrc1 frrc  --ipaddress=172.31.3.1 --macaddress=02:c1:c1:c1:c1:c1
ovs-docker add-port dp0 frrd1 frrd  --ipaddress=172.31.4.1 --macaddress=02:d1:d1:d1:d1:d1
ovs-docker add-port dp0 frra2 frra  --ipaddress=10.0.0.1 --macaddress=02:a2:a2:a2:a2:a2
ovs-docker add-port dp0 frrb2 frrb  --ipaddress=10.0.0.2 --macaddress=02:b2:b2:b2:b2:b2
ovs-docker add-port dp0 frrc2 frrc  --ipaddress=10.0.0.3 --macaddress=02:c2:c2:c2:c2:c2
ovs-docker add-port dp0 frrd2 frrd  --ipaddress=40.0.0.4 --macaddress=02:d2:d2:d2:d2:d2
ovs-docker add-port dp0 frra3 frra  --ipaddress=30.0.0.1 --macaddress=02:a3:a3:a3:a3:a3
ovs-docker add-port dp0 frrb3 frrb  --ipaddress=40.0.0.2 --macaddress=02:b3:b3:b3:b3:b3
ovs-docker add-port dp0 frrc3 frrc  --ipaddress=40.0.0.3 --macaddress=02:c3:c3:c3:c3:c3
ovs-docker add-port dp0 frrd3 frrd  --ipaddress=20.0.0.4 --macaddress=02:d3:d3:d3:d3:d3

#ovs-vsctl add-port dp0 rfrrvmD.4
ovs-docker add-port dp0 frra4 frra  --ipaddress=50.0.0.1 --macaddress=02:a4:a4:a4:a4:a4
ovs-docker add-port dp0 frrd4 frrd  --ipaddress=50.0.0.4 --macaddress=02:d4:d4:d4:d4:d4
ovs-vsctl set Bridge dp0 other-config:datapath-id=7266767372667673
ovs-vsctl set-controller dp0 tcp:127.0.0.1:$CONTROLLER_PORT
ovs-vsctl set Bridge dp0 protocols=OpenFlow13
ovs-ofctl -O OpenFlow13 add-flow dp0 actions=CONTROLLER:65509
