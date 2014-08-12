NUM_LUNS=10

set -e

parted -s /dev/vdb mktable msdos
cyls=$(parted -s /dev/vdb unit cyl print | grep 'Disk /' | sed -r 's/.*: ([0-9]+)cyl/\1/')
parted -s -a optimal /dev/vdb mkpart primary 0cyl ${cyls}cyl
partprobe
pvcreate /dev/vdb1
vgcreate vg1_storage /dev/vdb1
extents=$(vgdisplay vg1_storage | grep 'Total PE' | awk '{print $NF;}')
lvcreate -l$(($extents - 50)) -T vg1_storage/thinpool

create_lun () {
ID=$1

	lvcreate vg1_storage -V100G --thinpool vg1_storage/thinpool  -n lun${ID}_bdev;
	targetcli /backstores/block create name=lun${ID}_bdev dev=/dev/vg1_storage/lun${ID}_bdev;
	targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1/luns/ create /backstores/block/lun${ID}_bdev;
}


targetcli /iscsi create iqn.2014-07.org.ovirt:storage

for I in $(seq $NUM_LUNS);
do
	create_lun $(($I - 1));
done;

targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1 set attribute authentication=0
targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1 set attribute demo_mode_write_protect=0
targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1 set attribute generate_node_acls=1
targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1 set attribute cache_dynamic_acls=1
targetcli saveconfig

systemctl enable target
systemctl start target

iscsiadm -m discovery -t sendtargets -p 127.0.0.1
iscsiadm -m node -L all

systemctl start multipathd
systemctl enable multipathd
systemctl disable lvm2-lvmetad
systemctl stop lvm2-lvmetad
