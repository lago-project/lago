DIST=$(uname -r | sed -r  's/^.*\.([^\.]+)\.[^\.]+$/\1/')
ADDR=$(/sbin/ip -4 -o addr show dev eth0 | awk '{split($4,a,"."); print a[1] "." a[2] "." a[3] ".1"}')

# FIXME
# yum-config-manager --disable '*' &> /dev/null

cat > /etc/yum.repos.d/local-ovirt.repo <<EOF
[localsync]
name=Latest oVirt nightly
baseurl=http://$ADDR:8585/$DIST/
enabled=1
skip_if_unavailable=1
gpgcheck=0
EOF
