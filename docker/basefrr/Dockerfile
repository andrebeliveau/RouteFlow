FROM ubuntu:14.04
MAINTAINER NoviFlow Inc.(www.noviflow.com)
ARG DEBIAN_FRONTEND=noninteractive

COPY depot/frr_3.0.2-1-ubuntu14.04.1_amd64.deb .

RUN apt-get update
RUN apt-get -y upgrade
RUN apt-get -y install git autoconf g++ libtool openssl libssl-dev openssh-server 
RUN apt-get -y install \
    libboost-thread-dev libboost-system-dev libboost-filesystem-dev \
    libboost-program-options-dev libnl-3-dev libnl-route-3-dev \
    rsyslog vlan tcpdump telnet iperf libc-ares2
    
RUN dpkg -i /frr_3.0.2-1-ubuntu14.04.1_amd64.deb
RUN apt-get install -f
COPY client/run_rfclient.sh /root/.
COPY client/rfclient /.
RUN chmod +x rfclient