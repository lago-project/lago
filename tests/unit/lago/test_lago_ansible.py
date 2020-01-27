import lago.lago_ansible as lago_ansible
import pytest
import re

import six

# yapf: disable
VM1 = {
    'name': 'vm1',
    'groups': ['masters', 'vms'],
    'nics': [
        {
            'net': 'lago',
            'ip': '192.168.200.2'
        }
    ],
    'disks': [
        {
            'name': 'root',
            'format': 'qcow2',
            'template_name': 'el7',
            'type': 'template'
        }
    ],
    'vm-provider': 'local-libvirt',
    'vm-type': 'default',
    'mgmt_net': 'lago'
}

VM2 = {
    'name': 'vm2',
    'groups': ['vms'],
    'nics': [
        {
            'net': 'lago',
            'ip': '192.168.200.3'
        }
    ],
    'disks': [
        {
            'name': 'root',
            'format': 'qcow2',
            'template_name': 'el7',
            'type': 'template'
        }
    ],
    'vm-provider': 'local-libvirt',
    'vm-type': 'default',
    'mgmt_net': 'lago'
}

VM3 = {
    'name': 'vm3',
    'groups': [],
    'nics': [
        {
            'net': 'lago',
            'ip': '192.168.200.4'
        }
    ],
    'disks': [
        {
            'name': 'root',
            'format': 'qcow2',
            'template_name': 'fc25',
            'type': 'template'
        }
    ],
    'vm-provider': 'local-libvirt',
    'vm-type': 'not-default',
    'mgmt_net': 'lago'
}

# yapf: enable

VMS = [VM1, VM2, VM3]
ID_RSA = '/user/.lago/default/id_rsa'


def generate_prefix():
    vms = {vm['name']: VMMock(vm) for vm in VMS}
    return PrefixMock(vms, PathsMock())


def generate_entry(vm):
    return \
        '{} ansible_host={} ansible_ssh_private_key_file={}'.format(
            vm['name'], vm['nics'][0]['ip'], ID_RSA
        )


class PathsMock(object):
    def ssh_id_rsa(self):
        return ID_RSA


class PrefixMock(object):
    def __init__(self, vms, paths):
        self.vms = vms
        self.paths = paths

    def get_vms(self):
        return self.vms


class VMMock(object):
    def __init__(self, spec):
        self._spec = spec

    @property
    def spec(self):
        return self._spec

    def name(self):
        return self.spec['name']

    def ip(self):
        return self.spec['nics'][0]['ip']


class TestLagoAnsible(object):
    @pytest.fixture(scope='class')
    def lago_ansible_instance(self):
        return lago_ansible.LagoAnsible(generate_prefix())

    @pytest.mark.parametrize(
        'path, data_structure, expected', [
            ('/', VM3, VM3),
            ('', VM3, VM3),
            ('vm-provider', VM3, 'local-libvirt'),
            ('/disks/0/template_name', VM3, 'fc25'),
            ('/disks/-1/template_name', VM3, 'fc25'),
            ('groups/1/2/3', VM3, None),
        ]
    )
    def test_get_key(self, path, data_structure, expected):
        result = lago_ansible.LagoAnsible.get_key(path, data_structure)
        assert result == expected


# yapf: disable
    @pytest.mark.parametrize(
        'keys, expected', [
            (['/f'], {}), (
                None, {
                    'groups=masters': [
                        generate_entry(VM1),
                    ],
                    'groups=vms': [
                        generate_entry(VM1),
                        generate_entry(VM2),
                    ],
                    'vm-provider=local-libvirt': [
                        generate_entry(VM1),
                        generate_entry(VM2),
                        generate_entry(VM3),
                    ],
                    'vm-type=default': [
                        generate_entry(VM1),
                        generate_entry(VM2),
                    ],
                    'vm-type=not-default': [
                        generate_entry(VM3),
                    ],
                }
            ), (
                ['/disks/0/template_name', 'mgmt_net'], {
                    '/disks/0/template_name=el7': [
                        generate_entry(VM1),
                        generate_entry(VM2),
                    ],
                    '/disks/0/template_name=fc25': [generate_entry(VM3)],
                    'mgmt_net=lago': [
                        generate_entry(VM1),
                        generate_entry(VM2),
                        generate_entry(VM3),
                    ]
                }
            ), (
                [], {
                    'masters': [generate_entry(VM1)],
                    'vms': [generate_entry(VM1), generate_entry(VM2)]
                }
            )
        ]
    )
    # yapf: enable
    def test_get_inventory_temp_file(
        self, lago_ansible_instance, keys, expected
    ):
        hosts_dict = {}
        header_pattern = re.compile(r'^\[' r'([^\[\]]+)' r'\]$')
        current_header = None
        with lago_ansible_instance.get_inventory_temp_file(keys) as f:
            for line in f:
                m = header_pattern.match(line)
                if m:
                    # We've found a header, let's add it and continue to
                    # the next line
                    current_header = m.group(1)
                    hosts_dict[current_header] = list()
                else:
                    # We've found a host entry
                    hosts_dict[current_header].append(line.rstrip('\n'))

        for group in six.iterkeys(expected):
            assert sorted(expected[group]) == sorted(hosts_dict[group])
