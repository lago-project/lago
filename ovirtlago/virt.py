#
# Copyright 2015 Red Hat, Inc.
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
import os
import warnings

import lago
import lago.config
import lago.vm
import ovirtsdk.api
from ovirtsdk.infrastructure.errors import (RequestError, ConnectionError)

from . import (constants, testlib, )


class OvirtVirtEnv(lago.virt.VirtEnv):
    def __init__(self, prefix, vm_specs, net_spec):
        self._engine_vm = None
        self._host_vms = []
        self._ovirt_cpu_family = None
        super(OvirtVirtEnv, self).__init__(prefix, vm_specs, net_spec)

    def _create_vm(self, vm_spec):
        metadata = vm_spec.get('metadata', {})
        role = metadata.get('ovirt-role', None)
        if role:
            warnings.warn(
                'ovirt-role metadata entry will be soon deprecated, instead '
                'you should use the vm-provider entry in the domain '
                'definiton and set it no one of: ovirt-node, ovirt-engine, '
                'ovirt-host'
            )
            provider_name = 'ovirt-' + role
        else:
            provider_name = vm_spec.get(
                'vm-type',
                lago.config.get('default_vm_provider', 'default'),
            )

        if provider_name == 'ovirt-engine':
            if self._engine_vm is not None:
                raise RuntimeError('Engine VM already exists')

            vm_spec['vm-type'] = provider_name
            self._engine_vm = super(OvirtVirtEnv, self)._create_vm(vm_spec)
            return self._engine_vm

        elif provider_name in ('ovirt-host', 'ovirt-node'):
            vm_spec['vm-type'] = provider_name
            self._host_vms.append(
                super(OvirtVirtEnv, self)._create_vm(vm_spec)
            )
            return self._host_vms[-1]

        else:
            return super(OvirtVirtEnv, self)._create_vm(vm_spec)

    def engine_vm(self):
        return self._engine_vm

    def host_vms(self):
        return self._host_vms[:]

    def get_ovirt_cpu_family(self):
        ovirt_cpu_families = {
            'Broadwell': 'Intel Broadwell Family',
            'Broadwell-noTSX': 'Intel Broadwell-noTSX Family',
            'Haswell': 'Intel Haswell Family',
            'Haswell-noTSX': 'Intel Haswell-noTSX Family',
            'SandyBridge': 'Intel SandyBridge Family',
            'Westmere': 'Intel Westmere Family',
            'Nehalem': 'Intel Nehalem Family',
            'Penryn': 'Intel Penryn Family',
            'Conroe': 'Intel Conroe Family',
            'Opteron_G5': 'AMD Opteron G5',
            'Opteron_G4': 'AMD Opteron G4',
            'Opteron_G3': 'AMD Opteron G3',
            'Opteron_G2': 'AMD Opteron G2',
            'Opteron_G1': 'AMD Opteron G1',
        }

        if self._ovirt_cpu_family is None:
            cpu_model = super(OvirtVirtEnv, self).get_cpu_model()
            self._ovirt_cpu_family = ovirt_cpu_families.get(
                cpu_model, ovirt_cpu_families['Conroe']
            )
        return self._ovirt_cpu_family


# TODO : solve the problem of ssh to the Node
class NodeVM(lago.vm.DefaultVM):
    def _artifact_paths(self):
        return []

    def collect_artifacts(self, host_path):
        return

    def wait_for_ssh(self):
        return


class EngineVM(lago.vm.DefaultVM):
    def __init__(self, *args, **kwargs):
        super(EngineVM, self).__init__(*args, **kwargs)
        self._api = None

    def stop(self):
        super(EngineVM, self).stop()
        self._api = None

    def _artifact_paths(self):
        inherited_artifacts = super(EngineVM, self)._artifact_paths()
        return set(inherited_artifacts + ['/var/log/ovirt-engine', ])

    def _create_api(self):
        url = 'https://%s/ovirt-engine/api' % self.ip()
        return ovirtsdk.api.API(
            url=url,
            username=constants.ENGINE_USER,
            password=str(self.metadata['ovirt-engine-password']),
            validate_cert_chain=False,
            insecure=True,
        )

    def _get_api(self):
        try:
            api = []

            def get():
                instance = self._create_api()
                if instance:
                    api.append(instance)
                    return True
                return False

            testlib.assert_true_within_short(
                get,
                allowed_exceptions=[RequestError, ConnectionError],
            )
        except AssertionError:
            raise RuntimeError('Failed to connect to the engine')

        return api.pop()

    def get_api(self):
        if self._api is None or not self._api.test():
            self._api = self._get_api()
        return self._api

    def add_iso(self, path):
        iso_name = os.path.basename(path)
        self.copy_to(path, '.')
        ret = self.ssh(
            [
                'ovirt-iso-uploader',
                '--conf-file=/root/iso-uploader.conf',
                '--insecure',
                iso_name,
            ]
        )
        if ret:
            raise RuntimeError('Failed to upload iso to ovirt')
        ret = self.ssh(['rm', iso_name])
        if ret:
            raise RuntimeError('Failed to remove uploaded image')

    def engine_setup(self, config=None):
        self.wait_for_ssh()

        if config:
            self.copy_to(config, 'engine-answer-file')

        result = self.interactive_ssh(
            [
                'engine-setup',
            ] + (config and ['--config-append=engine-answer-file'] or []),
        )
        if result.code != 0:
            raise RuntimeError('Failed to setup the engine')


class HostVM(lago.vm.DefaultVM):
    def _artifact_paths(self):
        inherited_artifacts = super(HostVM, self)._artifact_paths()
        if self.distro() not in ['fc22', 'fc23']:
            inherited_artifacts.append('/var/log/messages')

        return set(
            inherited_artifacts + [
                '/var/log/vdsm',
                '/var/log/sanlock.log',
            ]
        )
