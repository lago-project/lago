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
import hashlib
import json
import logging
import os
import uuid

import lxml.etree

from . import (config, brctl, utils, log_utils, plugins, libvirt_utils, )

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


def _gen_ssh_command_id():
    return uuid.uuid1().hex[:8]


def _ip_to_mac(ip):
    # Mac addrs of domains are 54:52:xx:xx:xx:xx where the last 4 octets are
    # the hex repr of the IP address)
    mac_addr_pieces = [0x54, 0x52] + [int(y) for y in ip.split('.')]
    return ':'.join([('%02x' % x) for x in mac_addr_pieces])


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
                os.path.join(
                    host_path, os.path.basename(path)
                ),
            )


def _path_to_xml(basename):
    return os.path.join(os.path.dirname(__file__), basename, )


class VirtEnv(object):
    '''Env properties:
    * prefix
    * vms
    * net

    * libvirt_con
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
        for name, spec in net_specs.items():
            self._nets[name] = self._create_net(spec)

        self._vms = {}
        for name, spec in vm_specs.items():
            self._vms[name] = self._create_vm(spec)

        libvirt_url = config.get('libvirt_url')
        self.libvirt_con = libvirt_utils.get_libvirt_connection(
            name=self.uuid + libvirt_url,
            libvirt_url=libvirt_url,
        )

    def _create_net(self, net_spec):
        if net_spec['type'] == 'nat':
            cls = NATNetwork
        elif net_spec['type'] == 'bridge':
            cls = BridgeNetwork
        return cls(self, net_spec)

    def _create_vm(self, vm_spec):
        default_vm_type = config.get('default_vm_type')
        vm_type_name = vm_spec.get('vm-type', default_vm_type)
        vm_type = self.vm_types.get(vm_type_name)
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
        utils.invoke_in_parallel(lambda vm: vm.bootstrap(), self._vms.values())

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
                    set(
                        self._nets[net_name] for net_name in vm.nets()
                    )
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

    def stop(self, vm_names=None):
        if not vm_names:
            log_msg = 'Stop prefix'
            vms = self._vms.values()
            nets = self._nets.values()
        else:
            log_msg = 'Stop specified VMs'
            vms = [self._vms[vm_name] for vm_name in vm_names]
            stoppable_nets = set()
            for vm in vms:
                stoppable_nets = stoppable_nets.union(vm.nets())
            for vm in self._vms.values():
                if not vm.defined() or vm.name() in vm_names:
                    continue
                for net in vm.nets():
                    stoppable_nets.discard(net)
            nets = [self._nets[net] for net in stoppable_nets]

        with LogTask(log_msg):
            with LogTask('Stop vms'):
                for vm in vms:
                    vm.stop()
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
                    net
                    for net in self.get_nets().values() if net.is_management()
                ].pop()
            except IndexError:
                return self.get_nets().values().pop()

    def get_vms(self):
        return self._vms.copy()

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

        spec = {'nets': self._nets.keys(), 'vms': self._vms.keys(), }

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


class Network(object):
    def __init__(self, env, spec):
        self._env = env
        libvirt_url = config.get('libvirt_url')
        self.libvirt_con = libvirt_utils.get_libvirt_connection(
            name=env.uuid + libvirt_url,
            libvirt_url=libvirt_url,
        )
        self._spec = spec

    def name(self):
        return self._spec['name']

    def gw(self):
        return self._spec.get('gw')

    def is_management(self):
        return self._spec.get('management', False)

    def add_mappings(self, mappings):
        for name, ip, mac in mappings:
            self.add_mapping(name, ip, save=False)
        self.save()

    def add_mapping(self, name, ip, save=True):
        self._spec['mapping'][name] = ip
        if save:
            self.save()

    def resolve(self, name):
        return self._spec['mapping'][name]

    def _libvirt_name(self):
        return self._env.prefixed_name(self.name(), max_length=15)

    def alive(self):
        net_names = [net.name() for net in self.libvirt_con.listAllNetworks()]
        return self._libvirt_name() in net_names

    def start(self):
        if not self.alive():
            with LogTask('Create network %s' % self.name()):
                self.libvirt_con.networkCreateXML(self._libvirt_xml())

    def stop(self):
        if self.alive():
            with LogTask('Destroy network %s' % self.name()):
                self.libvirt_con.networkLookupByName(
                    self._libvirt_name(),
                ).destroy()

    def save(self):
        with open(self._env.virt_path('net-%s' % self.name()), 'w') as f:
            utils.json_dump(self._spec, f)


class NATNetwork(Network):
    def _libvirt_xml(self):
        with open(_path_to_xml('net_nat_template.xml')) as f:
            net_raw_xml = f.read()

        replacements = {
            '@NAME@': self._libvirt_name(),
            '@BR_NAME@': ('%s-nic' % self._libvirt_name())[:12],
            '@GW_ADDR@': self.gw(),
        }
        for k, v in replacements.items():
            net_raw_xml = net_raw_xml.replace(k, v, 1)

        net_xml = lxml.etree.fromstring(net_raw_xml)
        if 'dhcp' in self._spec:
            ip = net_xml.xpath('/network/ip')[0]

            def make_ip(last):
                return '.'.join(self.gw().split('.')[:-1] + [str(last)])

            dhcp = lxml.etree.Element('dhcp')
            ip.append(dhcp)

            dhcp.append(
                lxml.etree.Element(
                    'range',
                    start=make_ip(self._spec['dhcp']['start']),
                    end=make_ip(self._spec['dhcp']['end']),
                )
            )

            if self.is_management():
                for hostname, ip in self._spec['mapping'].items():
                    dhcp.append(
                        lxml.etree.Element(
                            'host',
                            mac=_ip_to_mac(ip),
                            ip=ip,
                            name=hostname
                        )
                    )
        return lxml.etree.tostring(net_xml)


class BridgeNetwork(Network):
    def _libvirt_xml(self):
        with open(_path_to_xml('net_br_template.xml')) as f:
            net_raw_xml = f.read()

        replacements = {
            '@NAME@': self._libvirt_name(),
            '@BR_NAME@': self._libvirt_name(),
        }
        for k, v in replacements.items():
            net_raw_xml = net_raw_xml.replace(k, v, 1)

        return net_raw_xml

    def start(self):
        if brctl.exists(self._libvirt_name()):
            return

        brctl.create(self._libvirt_name())
        try:
            super(BridgeNetwork, self).start()
        except:
            brctl.destroy(self._libvirt_name())

    def stop(self):
        super(BridgeNetwork, self).stop()
        if brctl.exists(self._libvirt_name()):
            brctl.destroy(self._libvirt_name())
