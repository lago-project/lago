#
# Copyright 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
from ovirtsdk.xml import params

from ovirtlago import testlib

MB = 2 ** 20
GB = 2 ** 30

TEST_DC = 'test-dc'
TEST_CLUSTER = 'test-cluster'
TEMPLATE_BLANK = 'Blank'
TEMPLATE_CENTOS7 = 'centos7_template'

VM0_NAME = 'vm0'
VM1_NAME = 'vm1'
DISK0_NAME = '%s_disk0' % VM0_NAME
DISK1_NAME = '%s_disk1' % VM1_NAME


@testlib.with_ovirt_api
def add_vm_blank(api):
    vm_params = params.VM(
        name=VM0_NAME,
        memory=1 * GB,
        cluster=params.Cluster(
            name=TEST_CLUSTER,
        ),
        template=params.Template(
            name=TEMPLATE_BLANK,
        ),
        display=params.Display(
            type_='spice',
        ),
    )
    api.vms.add(vm_params)
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM0_NAME).status.state == 'down',
    )


@testlib.with_ovirt_api
def add_nic(api):
    NIC_NAME = 'eth0'
    nic_params = params.NIC(
        name=NIC_NAME,
        interface='virtio',
        network=params.Network(
            name='ovirtmgmt',
        ),
    )
    api.vms.get(VM0_NAME).nics.add(nic_params)


@testlib.with_ovirt_api
def add_disk(api):
    disk_params = params.Disk(
        name=DISK0_NAME,
        size=10 * GB,
        provisioned_size=1,
        interface='virtio',
        format='cow',
        storage_domains=params.StorageDomains(
            storage_domain=[
                params.StorageDomain(
                    name='nfs',
                ),
            ],
        ),
        status=None,
        sparse=True,
        bootable=True,
    )
    api.vms.get(VM0_NAME).disks.add(disk_params)
    testlib.assert_true_within_short(
        lambda:
        api.vms.get(VM0_NAME).disks.get(DISK0_NAME).status.state == 'ok'
    )


@testlib.with_ovirt_api
def snapshot_merge(api):
    dead_snap1_params = params.Snapshot(
        description='dead_snap1',
        persist_memorystate=False,
        disks=params.Disks(
            disk=[
                params.Disk(
                    id=api.vms.get(VM0_NAME).disks.get(DISK0_NAME).id,
                ),
            ],
        ),
    )
    api.vms.get(VM0_NAME).snapshots.add(dead_snap1_params)
    testlib.assert_true_within_short(
        lambda:
        api.vms.get(VM0_NAME).snapshots.list()[-1].snapshot_status == 'ok'
    )

    dead_snap2_params = params.Snapshot(
        description='dead_snap2',
        persist_memorystate=False,
        disks=params.Disks(
            disk=[
                params.Disk(
                    id=api.vms.get(VM0_NAME).disks.get(DISK0_NAME).id,
                ),
            ],
        ),
    )
    api.vms.get(VM0_NAME).snapshots.add(dead_snap2_params)
    testlib.assert_true_within_short(
        lambda:
        api.vms.get(VM0_NAME).snapshots.list()[-1].snapshot_status == 'ok'
    )

    api.vms.get(VM0_NAME).snapshots.list()[-2].delete()
    testlib.assert_true_within_short(
        lambda:
        (len(api.vms.get(VM0_NAME).snapshots.list()) == 2) and
        (api.vms.get(VM0_NAME).snapshots.list()[-1].snapshot_status
         == 'ok'),
    )


@testlib.with_ovirt_api
def add_vm_template(api):
    vm_params = params.VM(
        name=VM1_NAME,
        memory=4 * GB,
        cluster=params.Cluster(
            name=TEST_CLUSTER,
        ),
        template=params.Template(
            name=TEMPLATE_CENTOS7,
        ),
        display=params.Display(
            type_='spice',
        ),
    )
    api.vms.add(vm_params)
    testlib.assert_true_within_long(
        lambda: api.vms.get(VM1_NAME).status.state == 'down',
    )
    disk_name = api.vms.get(VM1_NAME).disks.list()[0].name
    testlib.assert_true_within_long(
        lambda:
        api.vms.get(VM1_NAME).disks.get(disk_name).status.state == 'ok'
    )


@testlib.with_ovirt_prefix
def vm_run(prefix):
    api = prefix.virt_env.engine_vm().get_api()
    host_names = [h.name() for h in prefix.virt_env.host_vms()]

    start_params = params.Action(
        vm=params.VM(
            placement_policy=params.VmPlacementPolicy(
                host=params.Host(
                    name=sorted(host_names)[0]
                ),
            ),
        ),
    )
    api.vms.get(VM1_NAME).start(start_params)
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM1_NAME).status.state == 'up',
    )


@testlib.with_ovirt_prefix
def vm_migrate(prefix):
    api = prefix.virt_env.engine_vm().get_api()
    host_names = [h.name() for h in prefix.virt_env.host_vms()]

    migrate_params = params.Action(
        host=params.Host(
            name=sorted(host_names)[1]
        ),
    )
    api.vms.get(VM1_NAME).migrate(migrate_params)
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM1_NAME).status.state == 'up',
    )


@testlib.host_capability(['snapshot-live-merge'])
@testlib.with_ovirt_api
def snapshot_live_merge(api):
    disk = api.vms.get(VM1_NAME).disks.list()[0]
    disk_id = disk.id
    disk_name = disk.name

    live_snap1_params = params.Snapshot(
        description='live_snap1',
        persist_memorystate=True,
        disks=params.Disks(
            disk=[
                params.Disk(
                    id=disk_id,
                ),
            ],
        ),
    )
    api.vms.get(VM1_NAME).snapshots.add(live_snap1_params)
    testlib.assert_true_within_short(
        lambda:
        api.vms.get(VM1_NAME).snapshots.list()[-1].snapshot_status == 'ok'
    )

    live_snap2_params = params.Snapshot(
        description='live_snap2',
        persist_memorystate=True,
        disks=params.Disks(
            disk=[
                params.Disk(
                    id=disk_id,
                ),
            ],
        ),
    )
    api.vms.get(VM1_NAME).snapshots.add(live_snap2_params)
    for i, _ in enumerate(api.vms.get(VM1_NAME).snapshots.list()):
        testlib.assert_true_within_short(
            lambda:
            (api.vms.get(VM1_NAME).snapshots.list()[i].snapshot_status
             == 'ok')
        )

    api.vms.get(VM1_NAME).snapshots.list()[-2].delete()

    testlib.assert_true_within_long(
        lambda: len(api.vms.get(VM1_NAME).snapshots.list()) == 2,
    )

    for i, _ in enumerate(api.vms.get(VM1_NAME).snapshots.list()):
        testlib.assert_true_within_long(
            lambda:
            (api.vms.get(VM1_NAME).snapshots.list()[i].snapshot_status
             == 'ok'),
        )
    testlib.assert_true_within_short(
        lambda: api.vms.get(VM1_NAME).status.state == 'up'
    )

    testlib.assert_true_within_long(
        lambda:
        api.vms.get(VM1_NAME).disks.get(disk_name).status.state == 'ok'
    )


@testlib.with_ovirt_api
def hotplug_nic(api):
    nic2_params = params.NIC(
        name='eth1',
        network=params.Network(
            name='ovirtmgmt',
        ),
        interface='virtio',
    )
    api.vms.get(VM1_NAME).nics.add(nic2_params)


@testlib.with_ovirt_api
def hotplug_disk(api):
    disk2_params = params.Disk(
        name=DISK1_NAME,
        size=10 * GB,
        provisioned_size=1,
        interface='virtio',
        format='cow',
        storage_domains=params.StorageDomains(
            storage_domain=[
                params.StorageDomain(
                    name='nfs',
                ),
            ],
        ),
        status=None,
        sparse=True,
        bootable=False,
    )
    api.vms.get(VM1_NAME).disks.add(disk2_params)
    testlib.assert_true_within_short(
        lambda:
        api.vms.get(VM1_NAME).disks.get(DISK1_NAME).status.state == 'ok'
    )

_TEST_LIST = [
    add_vm_blank,
    add_nic,
    add_disk,
    snapshot_merge,
    add_vm_template,
    vm_run,
    vm_migrate,
    snapshot_live_merge,
    hotplug_nic,
    hotplug_disk,
]


def test_gen():
    for t in testlib.test_sequence_gen(_TEST_LIST):
        test_gen.__name__ = t.description
        yield t


def setup_module():
    testlib.get_test_prefix().revert_snapshots('ovirt-clean')
