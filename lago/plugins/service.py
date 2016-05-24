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
"""
Service Plugin
=================

This plugins are used in order to manage services in the vms

"""
from abc import (abstractmethod, abstractproperty, ABCMeta)

from enum import Enum

from . import Plugin


class ServiceState(Enum):
    #: This state corresponds to a service that is not available in the domain
    MISSING = 0
    INACTIVE = 1
    ACTIVE = 2


class ServicePlugin(Plugin):
    __metaclass__ = ABCMeta

    def __init__(self, vm, name):
        self._vm = vm
        self._name = name

    @abstractmethod
    def state(self):
        """
        Check the current status of the service

        Returns:
            ServiceState: Which state the service is at right now
        """
        pass

    @abstractmethod
    def _request_start(self):
        """
        Low level implementation of the service start request, used by the
        `func:start` method

        Returns:
            bool: True if the service succeeded to start, False otherwise
        """
        pass

    @abstractmethod
    def _request_stop(self):
        """
        Low level implementation of the service stop request, used by the
        `func:stop` method

        Returns:
            bool: True if the service succeeded to stop, False otherwise
        """
        pass

    @abstractproperty
    def BIN_PATH(self):
        """
        Path to the binary used to manage services in the vm, will be checked
        for existence when trying to decide if the serviece is supported on the
        VM (see `func:is_supported`).

        Returns:
            str: Full path to the binary insithe the domain
        """
        pass

    def exists(self):
        return self.state() != ServiceState.MISSING

    def alive(self):
        return self.state() == ServiceState.ACTIVE

    def start(self):
        state = self.state()
        if state == ServiceState.MISSING:
            raise RuntimeError('Service %s not present' % self._name)
        elif state == ServiceState.ACTIVE:
            return

        if self._request_start():
            raise RuntimeError('Failed to start service')

    def stop(self):
        state = self.state()
        if state == ServiceState.MISSING:
            raise RuntimeError('Service %s not present' % self._name)
        elif state == ServiceState.INACTIVE:
            return

        if self._request_stop():
            raise RuntimeError('Failed to stop service')

    @classmethod
    def is_supported(cls, vm):
        return vm.ssh(['test', '-e', cls.BIN_PATH]).code == 0
