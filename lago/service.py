#
# Copyright 2016 Red Hat, Inc.
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

from future.builtins import super
from lago.plugins.service import (
    ServicePlugin,
    ServiceState,
)


class SystemdService(ServicePlugin):
    BIN_PATH = '/usr/bin/systemctl'

    def _request_start(self):
        super()._request_start()
        return self._vm.ssh([self.BIN_PATH, 'start', self._name])

    def _request_stop(self):
        super()._request_stop()
        return self._vm.ssh([self.BIN_PATH, 'stop', self._name])

    def state(self):
        ret = self._vm.ssh([self.BIN_PATH, 'status --lines=0', self._name])
        if not ret:
            return ServiceState.ACTIVE

        lines = [l.strip() for l in ret.out.split('\n')]
        loaded = [l for l in lines if l.startswith('Loaded:')].pop()

        if loaded.split()[1] == 'loaded':
            return ServiceState.INACTIVE

        return ServiceState.MISSING


class SysVInitService(ServicePlugin):
    BIN_PATH = '/sbin/service'

    def _request_start(self):
        super()._request_start()
        return self._vm.ssh([self.BIN_PATH, self._name, 'start'])

    def _request_stop(self):
        super()._request_stop()
        return self._vm.ssh([self.BIN_PATH, self._name, 'stop'])

    def state(self):
        ret = self._vm.ssh([self.BIN_PATH, self._name, 'status'])

        if ret.code == 0:
            return ServiceState.ACTIVE

        if ret.out.strip().endswith('is stopped'):
            return ServiceState.INACTIVE

        return ServiceState.MISSING


class SystemdContainerService(ServicePlugin):
    BIN_PATH = '/usr/bin/docker'
    HOST_BIN_PATH = '/usr/bin/systemctl'

    def _request_start(self):
        super()._request_start()
        ret = self._vm.ssh(
            [self.BIN_PATH, 'exec vdsmc systemctl start', self._name]
        )

        if ret.code == 0:
            return ret

        return self._vm.ssh([self.HOST_BIN_PATH, 'start', self._name])

    def _request_stop(self):
        super()._request_stop()
        ret = self._vm.ssh(
            [self.BIN_PATH, 'exec vdsmc systemctl stop', self._name]
        )

        if ret.code == 0:
            return ret

        return self._vm.ssh([self.HOST_BIN_PATH, 'stop', self._name])

    def state(self):
        ret = self._vm.ssh(
            [
                self.BIN_PATH, 'exec vdsmc systemctl status --lines=0',
                self._name
            ]
        )
        if ret.code == 0:
            return ServiceState.ACTIVE

        lines = [l.strip() for l in ret.out.split('\n')]
        loaded = [l for l in lines if l.startswith('Loaded:')].pop()

        if loaded.split()[1] == 'loaded':
            return ServiceState.INACTIVE

        ret = self._vm.ssh([self.HOST_BIN_PATH, 'status', self._name])
        if ret.code == 0:
            return ServiceState.ACTIVE

        lines = [l.strip() for l in ret.out.split('\n')]
        loaded = [l for l in lines if l.startswith('Loaded:')].pop()

        if loaded.split()[1] == 'loaded':
            return ServiceState.INACTIVE

        return ServiceState.MISSING
