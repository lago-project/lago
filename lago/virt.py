#
# Copyright 2014-2017 Red Hat, Inc.
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
from copy import deepcopy
import functools
import hashlib
import json
import logging
import os
import uuid

import yaml
from future.builtins import super

from lago import log_utils, plugins, utils
from lago.config import config
from lago.providers.libvirt.network import BridgeNetwork, NATNetwork

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


class LagoUnknownVMTypeError(utils.LagoUserException):
    def __init__(self, vm_type_name, vm_types):
        super().__init__(
            'Unknown VM type: {0}, available types: {1}, \
            maybe you need to install lago plugin'
            .format(vm_type_name, vm_types)
        )


def _gen_ssh_command_id():
    return uuid.uuid1().hex[:8]


def _guestfs_copy_path(g, guest_path, host_path):
    if g.is_file(guest_path):
        with open(host_path, 'w') as f:
            f.write(g.read_file(guest_path))
    elif g.is_dir(guest_path):
        os.mkdir(host_path)
        for path in g.ls(guest_path):
            _guestfs_copy_path(
                g,
                os.path.join(
                    guest_path,
                    path,
                ),
                os.path.join(host_path, os.path.basename(path)),
            )


def _path_to_xml(basename):
    return os.path.join(
        os.path.dirname(__file__),
        basename,
    )


class VirtEnv(object):
    '''Env properties:
    * prefix
    * vms
    * net
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
        compat = self.get_compat()
        for name, spec in net_specs.items():
            self._nets[name] = self._create_net(spec, compat)

        self._vms = {}
        self._default_vm_type = config.get('default_vm_type')
        for name, spec in vm_specs.items():
            self._vms[name] = self._create_vm(spec)

    def _create_net(self, net_spec, compat):
        if net_spec['type'] == 'nat':
            cls = NATNetwork
        elif net_spec['type'] == 'bridge':
            cls = BridgeNetwork
        return cls(self, net_spec, compat=compat)

    def _create_vm(self, vm_spec):
        vm_type_name = vm_spec.get('vm-type', self._default_vm_type)
        try:
            vm_type = self.vm_types[vm_type_name]
        except KeyError:
            raise LagoUnknownVMTypeError(
                vm_type_name, ','.join(self.vm_types.keys())
            )
        vm_spec['vm-type'] = vm_type_name
        return vm_type(self, vm_spec)

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
        vms = filter(
            lambda vm: vm.spec.get('bootstrap', True), self._vms.values()
        )
        if vms:
            utils.invoke_in_parallel(lambda vm: vm.bootstrap(), vms)

    def export_vms(
        self,
        vms_names,
        standalone,
        dst_dir,
        compress,
        init_file_name,
        out_format,
        collect_only=False,
        with_threads=True
    ):
        # todo: move this logic to PrefixExportManager
        if not vms_names:
            vms_names = self._vms.keys()

        running_vms = []
        vms = []
        for name in vms_names:
            try:
                vm = self._vms[name]
                if not vm.spec.get('skip-export'):
                    vms.append(vm)
                    if vm.running():
                        running_vms.append(vm)
            except KeyError:
                raise utils.LagoUserException(
                    'Entity {} does not exist'.format(name)
                )

        if running_vms:
            raise utils.LagoUserException(
                'The following vms must be off:\n{}'.format(
                    '\n'.join([_vm.name() for _vm in running_vms])
                )
            )

        with LogTask('Exporting disks to: {}'.format(dst_dir)):
            if not os.path.isdir(dst_dir):
                os.mkdir(dst_dir)

            def _export_disks(vm):
                return vm.export_disks(
                    standalone, dst_dir, compress, collect_only, with_threads
                )

            if collect_only:
                return (
                    reduce(
                        lambda x, y: x.update(y) or x, map(_export_disks, vms)
                    )
                )
            else:
                if with_threads:
                    results = utils.invoke_in_parallel(_export_disks, vms)
                else:
                    results = map(_export_disks, vms)

                results = reduce(lambda x, y: x.update(y) or x, results)

        self.generate_init(
            os.path.join(dst_dir, init_file_name), out_format, vms
        )

        results['init-file'] = os.path.join(dst_dir, init_file_name)

        return results

    def generate_init(self, dst, out_format, vms_to_include, filters=None):
        """
        Generate an init file which represents this env and can
        be used with the images created by self.export_vms
        Args:
            dst (str): path and name of the new init file
            out_format (plugins.output.OutFormatPlugin):
                formatter for the output (the default is yaml)
            filters (list): list of paths to keys that should be removed from
                the init file
            vms_to_include (list of :class:lago.plugins.vm.VMPlugin):
                list of vms to include in the init file
        Returns:
            None
        """
        # todo: move this logic to PrefixExportManager
        with LogTask('Exporting init file to: {}'.format(dst)):
            # Set the default formatter to yaml. The default formatter
            # doesn't generate a valid init file, so it's not reasonable
            # to use it
            if isinstance(out_format, plugins.output.DefaultOutFormatPlugin):
                out_format = plugins.output.YAMLOutFormatPlugin()

            if not filters:
                filters = [
                    'domains/*/disks/*/metadata',
                    'domains/*/metadata/deploy-scripts', 'domains/*/snapshots',
                    'domains/*/name', 'nets/*/mapping', 'nets/*/dns_records'
                ]

            spec = self.get_env_spec(filters)
            temp = {}

            for vm in vms_to_include:
                temp[vm.name()] = spec['domains'][vm.name()]

            spec['domains'] = temp

            for _, domain in spec['domains'].viewitems():
                domain['disks'] = [
                    d for d in domain['disks'] if not d.get('skip-export')
                ]

                for disk in domain['disks']:
                    if disk['type'] == 'template':
                        disk['template_type'] = 'qcow2'
                    elif disk['type'] == 'empty':
                        disk['type'] = 'file'
                        disk['make_a_copy'] = 'True'

                    # Insert the relative path to the exported images
                    disk['path'] = os.path.join(
                        '$LAGO_INITFILE_PATH', os.path.basename(disk['path'])
                    )

            with open(dst, 'wt') as f:
                if isinstance(out_format, plugins.output.YAMLOutFormatPlugin):
                    # Dump the yaml file without type tags
                    # TODO: Allow passing parameters to output plugins
                    f.write(yaml.safe_dump(spec))
                else:
                    f.write(out_format.format(spec))

    def get_env_spec(self, filters=None):
        """
        Get the spec of the current env.
        The spec will hold the info about all the domains and
        networks associated with this env.
        Args:
            filters (list): list of paths to keys that should be removed from
                the init file
        Returns:
            dict: the spec of the current env
        """
        spec = {
            'domains':
                {
                    vm_name: deepcopy(vm_object.spec)
                    for vm_name, vm_object in self._vms.viewitems()
                },
            'nets':
                {
                    net_name: deepcopy(net_object.spec)
                    for net_name, net_object in self._nets.viewitems()
                }
        }

        if filters:
            utils.filter_spec(spec, filters)

        return spec

    def start(self, vm_names=None):
        if not vm_names:
            log_msg = 'Start Prefix'
            vms = self._vms.values()
            nets = self._nets.values()
        else:
            log_msg = 'Start specified VMs'
            vms = [self._vms[vm_name] for vm_name in vm_names]
            nets = set()
            for vm in vms:
                nets = nets.union(
                    set(self._nets[net_name] for net_name in vm.nets())
                )

        with LogTask(log_msg), utils.RollbackContext() as rollback:
            with LogTask('Start nets'):
                for net in nets:
                    net.start()
                    rollback.prependDefer(net.stop)

            with LogTask('Start vms'):
                for vm in vms:
                    vm.start()
                    rollback.prependDefer(vm.stop)
                rollback.clear()

    def _get_stop_shutdown_common_args(self, vm_names):
        """
        Get the common arguments for stop and shutdown commands
        Args:
            vm_names (list of str): The names of the requested vms
        Returns
            list of plugins.vm.VMProviderPlugin:
                vms objects that should be stopped
            list of virt.Network: net objects that should be stopped
            str: log message
        Raises:
            utils.LagoUserException: If a vm name doesn't exist
        """

        vms_to_stop = self.get_vms(vm_names).values()

        if not vm_names:
            log_msg = '{} prefix'
            nets = self._nets.values()
        else:
            log_msg = '{} specified VMs'
            nets = self._get_unused_nets(vms_to_stop)

        return vms_to_stop, nets, log_msg

    def _get_unused_nets(self, vms_to_stop):
        """
        Return a list of nets that used only by the vms in vms_to_stop
        Args:
            vms_to_stop (list of str): The names of the requested vms
        Returns
            list of virt.Network: net objects that used only by
                vms in vms_to_stop
        Raises:
            utils.LagoUserException: If a vm name doesn't exist
        """

        vm_names = [vm.name() for vm in vms_to_stop]
        unused_nets = set()

        for vm in vms_to_stop:
            unused_nets = unused_nets.union(vm.nets())
        for vm in self._vms.values():
            if not vm.running() or vm.name() in vm_names:
                continue
            for net in vm.nets():
                unused_nets.discard(net)
        nets = [self._nets[net] for net in unused_nets]

        return nets

    def stop(self, vm_names=None):

        vms, nets, log_msg = self._get_stop_shutdown_common_args(vm_names)

        with LogTask(log_msg.format('Stop')):
            with LogTask('Stop vms'):
                for vm in vms:
                    vm.stop()
            with LogTask('Stop nets'):
                for net in nets:
                    net.stop()

    def shutdown(self, vm_names, reboot=False):

        vms, nets, log_msg = self._get_stop_shutdown_common_args(vm_names)

        if reboot:
            with LogTask(log_msg.format('Reboot')):
                with LogTask('Reboot vms'):
                    for vm in vms:
                        vm.reboot()
        else:
            with LogTask(log_msg.format('Shutdown')):
                with LogTask('Shutdown vms'):
                    for vm in vms:
                        vm.shutdown()
                with LogTask('Stop nets'):
                    for net in nets:
                        net.stop()

    def get_nets(self):
        return self._nets.copy()

    def get_net(self, name=None):
        if name:
            return self.get_nets().get(name)
        else:
            try:
                return [
                    net for net in self.get_nets().values()
                    if net.is_management()
                ].pop()
            except IndexError:
                return self.get_nets().values().pop()

    def get_vms(self, vm_names=None):
        """
        Returns the vm objects associated with vm_names
        if vm_names is None, return all the vms in the prefix
        Args:
            vm_names (list of str): The names of the requested vms
        Returns
            dict: Which contains the requested vm objects indexed by name
        Raises:
            utils.LagoUserException: If a vm name doesn't exist
        """
        if not vm_names:
            return self._vms.copy()

        missing_vms = []
        vms = {}
        for name in vm_names:
            try:
                vms[name] = self._vms[name]
            except KeyError:
                # TODO: add resolver by suffix
                missing_vms.append(name)

        if missing_vms:
            raise utils.LagoUserException(
                'The following vms do not exist: \n{}'.format(
                    '\n'.join(missing_vms)
                )
            )

        return vms

    def get_vm(self, name):
        return self._vms[name]

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
        with LogTask('Save nets'):
            for net in self._nets.values():
                net.save()

        with LogTask('Save VMs'):
            for vm in self._vms.values():
                vm.save()

        spec = {
            'nets': self._nets.keys(),
            'vms': self._vms.keys(),
        }

        with LogTask('Save env'):
            with open(self.virt_path('env'), 'w') as f:
                utils.json_dump(spec, f)

    @log_task('Create VMs snapshots')
    def create_snapshots(self, name):
        utils.invoke_in_parallel(
            lambda vm: vm.create_snapshot(name),
            self._vms.values(),
        )

    @log_task('Revert VMs snapshots')
    def revert_snapshots(self, name):
        utils.invoke_in_parallel(
            lambda vm: vm.revert_snapshot(name),
            self._vms.values(),
        )

    def get_snapshots(self, domains=None):
        """
        Get the list of snapshots for each domain
        Args:
            domanins(list of str): list of the domains to get the snapshots
            for, all will be returned if none or empty list passed
        Returns:
            dict of str -> list(str): with the domain names and the list of
            snapshots for each
        """
        snapshots = {}
        for vm_name, vm in self.get_vms().items():
            if domains and vm_name not in domains:
                continue

            snapshots[vm_name] = vm._spec['snapshots']

        return snapshots

    def get_compat(self):
        """Get compatibility level for this environment - which is the Lago
        version used to create this environment """
        # Prior to version 0.37.0, the version which the environment was
        # initialized in was not saved, so we default to 0.36.
        return self.prefix.metadata.get('lago_version', '0.36.0')
