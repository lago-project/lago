set -e

cp /etc/sysconfig/network-scripts/ifcfg-eth0 /tmp/tmp
cat /tmp/tmp | grep -v HWADDR > /etc/sysconfig/network-scripts/ifcfg-eth0
rm -f /tmp/tmp

#get code
git clone https://gerrit.ovirt.org/ovirt-container-node
pushd ovirt-container-node

#build container
cat > repos/repo-custom.sh << EOF_main

#!/usr/bin/bash
yum install -y http://mirror.symnds.com/distributions/fedora-epel/7/x86_64/e/epel-release-7-5.noarch.rpm
cat > /etc/yum.repos.d/local-ovirt.repo << EOF
EOF_main
cat /etc/yum.repos.d/local-ovirt.repo >> repos/repo-custom.sh

echo "EOF" >> repos/repo-custom.sh

make centos7 repo-install=repos/repo-custom.sh
