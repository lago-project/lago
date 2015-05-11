set -e

cp /etc/sysconfig/network-scripts/ifcfg-eth0 /tmp/tmp
cat /tmp/tmp | grep -v HWADDR > /etc/sysconfig/network-scripts/ifcfg-eth0
rm -f /tmp/tmp

#install staff
systemctl status docker

#get code
env GIT_SSL_NO_VERIFY=true git clone https://code.engineering.redhat.com/gerrit/rhevh_container/

#build container
docker build -f rhevh_container/Vdsm.Dockerfile -t vdsmi:latest rhevh_container

atomic install vdsmi:latest

