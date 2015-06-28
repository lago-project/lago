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
import functools

import nose.tools as nt
from ovirtsdk.xml import params

from testenv import utils
from ovirttestenv import testlib

# DC/Cluster
DC_NAME = 'test-dc'
DC_VER_MAJ = '3'
DC_VER_MIN = '5'
CLUSTER_NAME = 'test-cluster'
CLUSTER_CPU_FAMILY = 'Intel Conroe Family'

# Storage
SD_NFS_NAME = 'nfs'
SD_NFS_ADDRESS = 'storage-nfs'
SD_NFS_PATH = '/exports/nfs_clean/share1'

SD_ISCSI_NAME = 'iscsi'
SD_ISCSI_ADDRESS = 'storage-iscsi'
SD_ISCSI_TARGET = 'iqn.2014-07.org.ovirt:storage'
SD_ISCSI_PORT = 3260
SD_ISCSI_NR_LUNS = 2

SD_ISO_NAME = 'iso'
SD_ISO_ADDRESS = 'storage-nfs'
SD_ISO_PATH = '/exports/iso'

SD_TEMPLATES_NAME = 'templates'
SD_TEMPLATES_ADDRESS = 'storage-nfs'
SD_TEMPLATES_PATH = '/exports/nfs_exported/share'


@testlib.with_ovirt_api
def add_dc(api):
    p = params.DataCenter(
        name=DC_NAME,
        local=False,
        version=params.Version(
            major=DC_VER_MAJ,
            minor=DC_VER_MIN,
        ),
    )
    nt.assert_true(api.datacenters.add(p))


@testlib.with_ovirt_api
def add_cluster(api):
    p = params.Cluster(
        name=CLUSTER_NAME,
        cpu=params.CPU(
            id=CLUSTER_CPU_FAMILY,
        ),
        version=params.Version(
            major=DC_VER_MAJ,
            minor=DC_VER_MIN,
        ),
        data_center=params.DataCenter(
            name=DC_NAME,
        ),
    )
    nt.assert_true(api.clusters.add(p))


@testlib.with_ovirt_prefix
def add_hosts(prefix):
    api = prefix.virt_env.engine_vm().get_api()

    def _add_host(vm):
        p = params.Host(
            name=vm.name(),
            address=vm.name(),
            cluster=params.Cluster(
                name=CLUSTER_NAME,
            ),
            root_password=vm.root_password(),
            override_iptables=True,
        )

        return api.hosts.add(p)

    hosts = prefix.virt_env.host_vms()
    vec = utils.func_vector(_add_host, [(h,) for h in hosts])
    vt = utils.VectorThread(vec)
    vt.start_all()
    nt.assert_true(all(vt.join_all()))

    for host in hosts:
        testlib.assert_true_within_long(
            lambda: api.hosts.get(host.name()).status.state == 'up',
        )


def _add_storage_domain(api, p):
    dc = api.datacenters.get(DC_NAME)
    sd = api.storagedomains.add(p)
    nt.assert_true(sd)
    nt.assert_true(
        api.datacenters.get(
            DC_NAME,
        ).storagedomains.add(
            api.storagedomains.get(
                sd.name,
            ),
        )
    )

    if dc.storagedomains.get(sd.name).status.state == 'maintenance':
        sd.activate()
        testlib.assert_true_within_long(
            lambda: dc.starage_domains.get(sd.name).status.state == 'active'
        )


@testlib.with_ovirt_api
def add_master_storage_domain(api):
    p = params.StorageDomain(
        name=SD_NFS_NAME,
        data_center=params.DataCenter(
            name=DC_NAME,
        ),
        type_='data',
        storage_format='v3',
        host=params.Host(
            name=api.hosts.list().pop().name,
        ),
        storage=params.Storage(
            type_='nfs',
            address=SD_NFS_ADDRESS,
            path=SD_NFS_PATH,
        ),
    )
    _add_storage_domain(api, p)


@testlib.with_ovirt_prefix
def add_secondary_storage_domains(prefix):
    api = prefix.virt_env.engine_vm().get_api()
    vt = utils.VectorThread(
        [
            functools.partial(add_iscsi_storage_domain, prefix),
            functools.partial(add_iso_storage_domain, api),
            functools.partial(add_templates_storage_domain, api),
        ],
    )
    vt.start_all()
    vt.join_all()


def add_iscsi_storage_domain(prefix):
    api = prefix.virt_env.engine_vm().get_api()

    # Find LUN GUIDs
    ret = prefix.virt_env.get_vm('storage-iscsi').ssh(
        ['multipath', '-ll'],
    )
    nt.assert_equals(ret.code, 0)

    lun_guids = [
        line.split()[0]
        for line in ret.out.split('\n')
        if line.find('LIO-ORG') != -1
    ]

    lun_guids = lun_guids[:SD_ISCSI_NR_LUNS]

    p = params.StorageDomain(
        name=SD_ISCSI_NAME,
        data_center=params.DataCenter(
            name=DC_NAME,
        ),
        type_='data',
        storage_format='v3',
        host=params.Host(
            name=api.hosts.list().pop().name,
        ),
        storage=params.Storage(
            type_='iscsi',
            volume_group=params.VolumeGroup(
                logical_unit=[
                    params.LogicalUnit(
                        id=lun_id,
                        address=SD_ISCSI_ADDRESS,
                        port=SD_ISCSI_PORT,
                        target=SD_ISCSI_TARGET,
                    ) for lun_id in lun_guids
                ]

            ),
        ),
    )
    _add_storage_domain(api, p)


def add_iso_storage_domain(api):
    p = params.StorageDomain(
        name=SD_ISO_NAME,
        data_center=params.DataCenter(
            name=DC_NAME,
        ),
        type_='iso',
        host=params.Host(
            name=api.hosts.list().pop().name,
        ),
        storage=params.Storage(
            type_='nfs',
            address=SD_ISO_ADDRESS,
            path=SD_ISO_PATH,
        ),
    )
    _add_storage_domain(api, p)


def add_templates_storage_domain(api):
    p = params.StorageDomain(
        name=SD_TEMPLATES_NAME,
        data_center=params.DataCenter(
            name=DC_NAME,
        ),
        type_='data',
        storage_format='v3',
        host=params.Host(
            name=api.hosts.list().pop().name
        ),
        storage=params.Storage(
            type_='nfs',
            address=SD_TEMPLATES_ADDRESS,
            path=SD_TEMPLATES_PATH,
        ),
    )
    _add_storage_domain(api, p)


@testlib.with_ovirt_api
def import_templates(api):
    templates = api.storagedomains.get(
        'templates',
    ).templates.list(
        unregistered=True,
    )

    for template in templates:
        template.register(
            action=params.Action(
                cluster=params.Cluster(
                    name=CLUSTER_NAME,
                ),
            ),
        )

    for template in api.templates.list():
        testlib.assert_true_within_short(
            lambda: api.templates.get(template.name).status.state == 'ok',
        )

_TEST_LIST = [
    add_dc,
    add_cluster,
    add_hosts,
    add_master_storage_domain,
    add_secondary_storage_domains,
    import_templates,
]


def test_gen():
    for t in testlib.test_sequence_gen(_TEST_LIST):
        test_gen.__name__ = t.description
        yield t
