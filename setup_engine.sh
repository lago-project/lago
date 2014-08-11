cat > /etc/yum.repos.d/local-ovirt.repo <<EOF
[ovirt-master-snapshot]
name=Latest oVirt nightly
baseurl=http://192.168.111.1/ovirt-master-snapshot/
enabled=1
skip_if_unavailable=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-ovirt-3.5

[ovirt-master-snapshot-static]
name=Latest oVirt master additional nightly snapshot
baseurl=http://192.168.111.1/ovirt-master-snapshot-static/
enabled=1
skip_if_unavailable=1
gpgcheck=0

[ovirt-master-patternfly1]
name=Copr repo for patternfly1 owned by patternfly
baseurl=http://192.168.111.1/ovirt-master-patternfly1
enabled=1
skip_if_unavailable=1
gpgcheck=0


EOF

cat > /root/engine-answer-file <<EOF
# action=setup
[environment:default]
OVESETUP_DIALOG/confirmSettings=bool:True
OVESETUP_CONFIG/applicationMode=str:both
OVESETUP_CONFIG/updateFirewall=bool:False
OVESETUP_CONFIG/fqdn=str:engine
OVESETUP_CONFIG/storageType=str:nfs
OVESETUP_CONFIG/adminPassword=str:123
OVESETUP_CONFIG/firewallManager=none:None
OSETUP_RPMDISTRO/requireRollback=none:None
OSETUP_RPMDISTRO/enableUpgrade=none:None
OVESETUP_DB/database=str:engine
OVESETUP_DB/fixDbViolations=none:None
OVESETUP_DB/secured=bool:False
OVESETUP_DB/host=str:localhost
OVESETUP_DB/user=str:engine
OVESETUP_DB/securedHostValidation=bool:False
OVESETUP_DB/password=str:CIKfimkn57xN7c5VwcFeU4
OVESETUP_DB/port=int:5432
OVESETUP_ENGINE_CORE/enable=bool:True
OVESETUP_CORE/engineStop=none:None
OVESETUP_SYSTEM/memCheckEnabled=bool:True
OVESETUP_SYSTEM/nfsConfigEnabled=bool:False
OVESETUP_PKI/organization=str:Test
OVESETUP_CONFIG/isoDomainMountPoint=none:None
OVESETUP_CONFIG/isoDomainName=none:None
OVESETUP_CONFIG/isoDomainACL=none:None
OVESETUP_AIO/configure=none:None
OVESETUP_AIO/storageDomainDir=none:None
OVESETUP_PROVISIONING/postgresProvisioningEnabled=bool:True
OVESETUP_APACHE/configureRootRedirection=bool:True
OVESETUP_APACHE/configureSsl=bool:True
OVESETUP_CONFIG/websocketProxyConfig=bool:True
EOF

yum install --nogpgcheck -y ovirt-engine

engine-setup --config=/root/engine-answer-file --jboss-home=/usr/share/ovirt-engine-jboss-as
