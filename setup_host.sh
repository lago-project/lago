yum install -y tar
cp /etc/sysconfig/network-scripts/ifcfg-eth0 /tmp/tmp
cat /tmp/tmp | sed '7d' > /etc/sysconfig/network-scripts/ifcfg-eth0
