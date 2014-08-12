set -e

cat > /root/iso-uploader.conf << EOF
[ISOUploader]
user=admin@internal
passwd=123
engine=localhost:443
EOF

yum install --nogpgcheck -y ovirt-engine
