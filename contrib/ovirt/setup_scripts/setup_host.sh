set -e

cp /etc/sysconfig/network-scripts/ifcfg-eth0 /tmp/tmp
cat /tmp/tmp | grep -v HWADDR > /etc/sysconfig/network-scripts/ifcfg-eth0
rm -f /tmp/tmp


yum install --nogpgcheck -y vdsm

