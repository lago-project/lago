#
# Copyright 2016-2017 Red Hat, Inc.
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

from lago.plugins import vm
from lago import ssh


class DefaultVM(vm.VMPlugin):
    pass


class SSHVMProvider(vm.VMProviderPlugin):
    def start(self, *args, **kwargs):
        pass

    def stop(self, *args, **kwargs):
        pass

    def defined(self, *args, **kwargs):
        return True

    def bootstrap(self, *args, **kwargs):
        pass

    def state(self, *args, **kwargs):
        return 'running'

    def running(self, *args, **kwargs):
        try:
            ssh.get_ssh_client(
                ip_addr=self.vm.ip(),
                host_name=self.vm.name(),
                propagate_fail=False,
                ssh_tries=1,
                ssh_key=self.vm.virt_env.prefix.paths.ssh_id_rsa(),
                username=self.vm._spec.get('ssh-user'),
                password=self.vm._spec.get('ssh-password'),
            )
        except ssh.LagoSSHTimeoutException:
            return False

        return True

    def create_snapshot(self, name, *args, **kwargs):
        pass

    def revert_snapshot(self, name, *args, **kwargs):
        pass
