set -e

parted -s /dev/vdb mktable msdos
cyls=$(parted -s /dev/vdb unit cyl print | grep 'Disk /' | sed -r 's/.*: ([0-9]+)cyl/\1/')
parted -s -a optimal /dev/vdb mkpart primary 0cyl ${cyls}cyl
partprobe
pvcreate /dev/vdb1
vgcreate vg1_storage /dev/vdb1
extents=$(vgdisplay vg1_storage | grep 'Total PE' | awk '{print $NF;}')
lvcreate -l $(($extents - 50)) -T vg1_storage/thinpool
lvcreate vg1_storage -V100G --thinpool vg1_storage/thinpool  -n nfs
mkfs.ext4 /dev/mapper/vg1_storage-nfs
mkdir -p			\
        /exports/nfs_clean/	\
        /exports/nfs_exported/
echo '/dev/mapper/vg1_storage-nfs       /exports/nfs_clean   	ext4    defaults        0 0' >> /etc/fstab
echo '/dev/vdc1			        /exports/nfs_exported   ext4    defaults        0 0' >> /etc/fstab
mount -a

mkdir -p 				\
	/exports/nfs_clean/share1/ 	\
	/exports/nfs_clean/iso/

chmod a+rwx 				\
	/exports/nfs_clean/share1/	\
	/exports/nfs_clean/iso/

echo '/exports/nfs_clean/share1 *(rw,sync,no_root_squash,no_all_squash)' >> /etc/exports
echo '/exports/nfs_exported/ *(rw,sync,no_root_squash,no_all_squash)' >> /etc/exports
exportfs -a

systemctl start rpcbind.service
systemctl start nfs-server.service
systemctl start nfs-lock.service
systemctl start nfs-idmap.service
systemctl enable rpcbind.service
systemctl enable nfs-server.service
systemctl enable nfs-lock.service
systemctl enable nfs-idmap.service
