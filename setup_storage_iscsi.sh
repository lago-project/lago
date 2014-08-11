parted -s /dev/vdb mktable msdos
cyls=$(parted -s /dev/vdb unit cyl print | grep 'Disk /' | sed -r 's/.*: ([0-9]+)cyl/\1/')
parted -s -a optimal /dev/vdb mkpart primary 0cyl ${cyls}cyl
partprobe
pvcreate /dev/vdb1
vgcreate vg1_storage /dev/vdb1
extents=$(vgdisplay vg1_storage | grep 'Total PE' | awk '{print $NF;}')
lvcreate vg1_storage -l $(($extents / 2)) -n lun0_bdev
lvcreate vg1_storage -l $(($extents / 2)) -n lun1_bdev

yum install -y targetcli

targetcli /backstores/block create name=lun0_bdev dev=/dev/vg1_storage/lun0_bdev
targetcli /backstores/block create name=lun1_bdev dev=/dev/vg1_storage/lun1_bdev
targetcli /iscsi create iqn.2014-07.org.ovirt:storage

targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1/luns/ create /backstores/block/lun0_bdev
targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1/luns/ create /backstores/block/lun1_bdev
targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1/portals create 0.0.0.0
targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1 set attribute authentication=0
targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1 set attribute demo_mode_write_protect=0
targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1 set attribute generate_node_acls=1
targetcli /iscsi/iqn.2014-07.org.ovirt:storage/tpg1 set attribute cache_dynamic_acls=1
targetcli saveconfig

systemctl enable target
systemctl start target
