FROM basefrr
MAINTAINER NoviFlow Inc.(www.noviflow.com)
ARG DEBIAN_FRONTEND=noninteractive

ADD /etc /etc
ENTRYPOINT ["bash","--init-file","/root/run_rfclient.sh"]
