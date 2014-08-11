parted -s /dev/vdb mktable msdos
cyls=$(parted -s /dev/vdb unit cyl print | grep 'Disk /' | sed -r 's/.*: ([0-9]+)cyl/\1/')
parted -s -a optimal /dev/vdb mkpart primary 0cyl ${cyls}cyl
partprobe
pvcreate /dev/vdb1
vgcreate vg1_storage /dev/vdb1
extents=$(vgdisplay vg1_storage | grep 'Total PE' | awk '{print $NF;}')
lvcreate vg1_storage -l $extents -n nfs
mkfs.ext4 /dev/mapper/vg1_storage-nfs
mkdir -p /exports/
echo '/dev/mapper/vg1_storage-nfs       /exports/   ext4    defaults        0 0' >> /etc/fstab
mount -a
mkdir -p /exports/nfs/
chmod a+rwx /exports/nfs/
yum install -y nfs-utils

echo '/exports/nfs *(rw,sync,no_root_squash,no_all_squash)' >> /etc/exports
exportfs -a

systemctl start rpcbind.service
systemctl start nfs-server.service
systemctl start nfs-lock.service
systemctl start nfs-idmap.service
systemctl enable rpcbind.service
systemctl enable nfs-server.service
systemctl enable nfs-lock.service
systemctl enable nfs-idmap.service
