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

import ovirtsdk.api
import testenv

import constants
import utils
import testlib


class OvirtVirtEnv(testenv.virt.VirtEnv):
    def __init__(self, prefix, vm_specs, net_spec):
        self._engine_vm = None
        self._host_vms = []
        super(OvirtVirtEnv, self).__init__(prefix, vm_specs, net_spec)

    def _create_vm(self, vm_spec):
        metadata = vm_spec.get('metadata', {})
        role = metadata.get('ovirt-role', None)
        if role == 'engine':
            if self._engine_vm is not None:
                raise RuntimeError('Engine VM already exists')
            self._engine_vm = EngineVM(self, vm_spec)
            return self._engine_vm
        elif role == 'host':
            self._host_vms.append(HostVM(self, vm_spec))
            return self._host_vms[-1]
        else:
            return TestVM(self, vm_spec)

    def engine_vm(self):
        return self._engine_vm

    def host_vms(self):
        return self._host_vms[:]


class TestVM(testenv.virt.VM):
    def _artifact_paths(self):
        return []

    def collect_artifacts(self, host_path):
        self.extract_paths(
            [
                (
                    guest_path,
                    os.path.join(host_path, guest_path.replace('/', '_')),
                ) for guest_path in self._artifact_paths()
            ]
        )

    def ssh(self, *args, **kwargs):
        with utils.repo_server_context(self.virt_env().prefix()):
            super(TestVM, self).ssh(*args, **kwargs)

    def interactive_ssh(self, *args, **kwargs):
        with utils.repo_server_context(self.virt_env().prefix()):
            super(TestVM, self).interactive_ssh(*args, **kwargs)


class EngineVM(TestVM):
    def __init__(self, *args, **kwargs):
        TestVM.__init__(self, *args, **kwargs)
        self._api = None

    def stop(self):
        TestVM.stop(self)
        self._api = None

    def _artifact_paths(self):
        return [
            '/var/log/ovirt-engine',
        ]

    def _create_api(self):
        url = 'https://%s/ovirt-engine/api' % self.ip()
        return ovirtsdk.api.API(
            url=url,
            username=constants.ENGINE_USER,
            password=self.metadata['ovirt-engine-password'],
            validate_cert_chain=False,
            insecure=True,
            persistent_auth=False,
        )

    def _get_api(self, wait):
        if wait:
            self.wait_for_ssh()
            try:
                testlib.assert_true_within_long(
                    lambda:
                        self.service('ovirt-engine').alive()
                )
                testlib.assert_true_within_short(
                    lambda: self._create_api().disconnect() or True
                )
            except AssertionError:
                raise RuntimeError('Failed to connect to the engine')
        return self._create_api()

    def get_api(self, wait=True):
        if self._api is None:
            self._api = self._get_api(wait)
        return self._api

    def add_iso(self, path):
        iso_name = os.path.basename(path)
        ret, _, _ = self.scp_to(path, '.')
        if ret != 0:
            raise RuntimeError('Failed to copy iso to engine')
        ret, _, _ = self.ssh(
            [
                'ovirt-iso-uploader',
                '--conf-file=/root/iso-uploader.conf',
                '--insecure',
                iso_name,
            ]
        )
        if ret != 0:
            raise RuntimeError('Failed to upload iso to ovirt')
        self.ssh(['rm', iso_name])

    def engine_setup(self, config=None):
        self.wait_for_ssh()

        if config:
            self.scp_to(config, 'engine-answer-file')

        self.interactive_ssh(
            [
                'engine-setup',
                '--jboss-home=/usr/share/ovirt-engine-jboss-as',
            ] + (config and ['--config=engine-answer-file'] or []),
        )


class HostVM(TestVM):
    def _artifact_paths(self):
        return [
            '/var/log/vdsm',
        ]
