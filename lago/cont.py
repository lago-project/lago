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
import functools
import hashlib
import json
import logging

from . import (config, utils, log_utils, plugins, docker_utils, )

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


class ContEnv(object):
    '''Env properties:
    * prefix
    * vms
    * net

    * docker_con
    '''

    def __init__(self, prefix, vm_specs, net_specs):
        self.vm_types = plugins.load_plugins(
            plugins.PLUGIN_ENTRY_POINTS['vm'],
            instantiate=False,
        )
        self.prefix = prefix

        with open(self.prefix.paths.uuid(), 'r') as uuid_fd:
            self.uuid = uuid_fd.read().strip()

        self._nets = {}
        self._vms = {}

        docker_url = config.get('docker_url')
        self.docker_client = docker_utils.get_docker_client(
            name=self.uuid + docker_url,
            docker_url=docker_url,
        )

    def prefixed_name(self, unprefixed_name, max_length=0):
        """
        Returns a uuid pefixed identifier

        Args:
            unprefixed_name(str): Name to add a prefix to
            max_length(int): maximum length of the resultant prefixed name,
                will adapt the given name and the length of the uuid ot fit it

        Returns:
            str: prefixed identifier for the given unprefixed name
        """
        if max_length == 0:
            prefixed_name = '%s-%s' % (self.uuid[:8], unprefixed_name)
        else:
            if max_length < 6:
                raise RuntimeError(
                    "Can't prefix with less than 6 chars (%s)" %
                    unprefixed_name
                )
            if max_length < 16:
                _uuid = self.uuid[:4]
            else:
                _uuid = self.uuid[:8]

            name_max_length = max_length - len(_uuid) - 1

            if name_max_length < len(unprefixed_name):
                hashed_name = hashlib.sha1(unprefixed_name).hexdigest()
                unprefixed_name = hashed_name[:name_max_length]

            prefixed_name = '%s-%s' % (_uuid, unprefixed_name)

        return prefixed_name

    def virt_path(self, *args):
        return self.prefix.paths.virt(*args)

    def bootstrap(self):
        pass

    def start(self, vm_names=None):
        pass

    def stop(self, vm_names=None):
        pass

    @classmethod
    def from_prefix(cls, prefix):
        virt_path = functools.partial(prefix.paths.prefixed, 'virt')

        with open(virt_path('env'), 'r') as f:
            env_dom = json.load(f)

        net_specs = {}
        for name in env_dom['nets']:
            with open(virt_path('net-%s' % name), 'r') as f:
                net_specs[name] = json.load(f)

        vm_specs = {}
        for name in env_dom['vms']:
            with open(virt_path('vm-%s' % name), 'r') as f:
                vm_specs[name] = json.load(f)

        return cls(prefix, vm_specs, net_specs)

    @log_task('Save prefix')
    def save(self):

        spec = {'nets': self._nets.keys(), 'vms': self._vms.keys(), }

        with LogTask('Save env'):
            with open(self.virt_path('env'), 'w') as f:
                utils.json_dump(spec, f)
