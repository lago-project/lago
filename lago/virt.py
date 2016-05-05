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
import collections
import contextlib
import functools
import hashlib
import json
import logging
import os
import pwd
import socket
import time
import uuid

import guestfs
import libvirt
import lxml.etree
import paramiko
from scp import SCPClient

import config
import brctl
import utils
import sysprep
from . import log_utils
from . import libvirt_utils

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)

#: Url to the libvirt daemon
LIBVIRT_URL = 'qemu:///system'


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
        self.prefix = prefix

        with open(self.prefix.paths.uuid(), 'r') as f:
            self._uuid = f.read().strip()

        self._nets = {}
        for name, spec in net_specs.items():
            self._nets[name] = self._create_net(spec)

        self._vms = {}
        for name, spec in vm_specs.items():
            self._vms[name] = self._create_vm(spec)

        self._libvirt_con = None

    def _create_net(self, net_spec):
        if net_spec['type'] == 'nat':
            cls = NATNetwork
        elif net_spec['type'] == 'bridge':
            cls = BridgeNetwork
        return cls(self, net_spec)

    def _create_vm(self, vm_spec):
        return VM(self, vm_spec)

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
            prefixed_name = '%s-%s' % (self._uuid[:8], unprefixed_name)
        else:
            if max_length < 6:
                raise RuntimeError(
                    "Can't prefix with less than 6 chars (%s)" %
                    unprefixed_name
                )
            if max_length < 16:
                _uuid = self._uuid[:4]
            else:
                _uuid = self._uuid[:8]

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

    @property
    def libvirt_con(self):
        if self._libvirt_con is None:
            self._libvirt_con = libvirt.open(LIBVIRT_URL)
        return self._libvirt_con

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
        net_names = [
            net.name() for net in self._env.libvirt_con.listAllNetworks()
        ]
        return self._libvirt_name() in net_names

    def start(self):
        if not self.alive():
            with LogTask('Create network %s' % self.name()):
                self._env.libvirt_con.networkCreateXML(self._libvirt_xml())

    def stop(self):
        if self.alive():
            with LogTask('Destroy network %s' % self.name()):
                self._env.libvirt_con.networkLookupByName(
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


class ServiceState:
    MISSING = 0
    INACTIVE = 1
    ACTIVE = 2


class _Service:
    def __init__(self, vm, name):
        self._vm = vm
        self._name = name

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


class _SystemdService(_Service):
    BIN_PATH = '/usr/bin/systemctl'

    def _request_start(self):
        return self._vm.ssh([self.BIN_PATH, 'start', self._name])

    def _request_stop(self):
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


class _SysVInitService(_Service):
    BIN_PATH = '/sbin/service'

    def _request_start(self):
        return self._vm.ssh([self.BIN_PATH, self._name, 'start'])

    def _request_stop(self):
        return self._vm.ssh([self.BIN_PATH, self._name, 'stop'])

    def state(self):
        ret = self._vm.ssh([self.BIN_PATH, self._name, 'status'])

        if ret.code == 0:
            return ServiceState.ACTIVE

        if ret.out.strip().endswith('is stopped'):
            return ServiceState.INACTIVE

        return ServiceState.MISSING


class _SystemdContainerService(_Service):
    BIN_PATH = '/usr/bin/docker'
    HOST_BIN_PATH = '/usr/bin/systemctl'

    def _request_start(self):
        ret = self._vm.ssh(
            [self.BIN_PATH, 'exec vdsmc systemctl start', self._name]
        )

        if ret.code == 0:
            return ret

        return self._vm.ssh([self.HOST_BIN_PATH, 'start', self._name])

    def _request_stop(self):
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


_SERVICE_WRAPPERS = collections.OrderedDict()
_SERVICE_WRAPPERS['systemd_container'] = _SystemdContainerService
_SERVICE_WRAPPERS['systemd'] = _SystemdService
_SERVICE_WRAPPERS['sysvinit'] = _SysVInitService


class VM(object):
    '''VM properties:
    * name
    * cpus
    * memory
    * disks
    * metadata
    * network/mac addr
    '''

    def __init__(self, env, spec):
        self._env = env
        self._spec = self._normalize_spec(spec.copy())

        self._service_class = _SERVICE_WRAPPERS.get(
            self._spec.get('service_class', None),
            None,
        )
        self._ssh_client = None

    def virt_env(self):
        return self._env

    @classmethod
    def _normalize_spec(cls, spec):
        spec['snapshots'] = spec.get('snapshots', {})
        spec['metadata'] = spec.get('metadata', {})

        if 'root-password' not in spec:
            spec['root-password'] = config.get('default_root_password')

        return spec

    def _open_ssh_client(self):
        while self._ssh_client is None:
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy(), )
                client.connect(
                    self.ip(),
                    username='root',
                    key_filename=self._env.prefix.paths.ssh_id_rsa(),
                    timeout=1,
                )
                return client
            except socket.error:
                pass
            except socket.timeout:
                pass

    def _check_defined(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.defined():
                raise RuntimeError('VM %s is not defined' % self.name())
            return func(self, *args, **kwargs)

        return wrapper

    def _check_alive(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.alive():
                raise RuntimeError('VM %s is not running' % self.name())
            return func(self, *args, **kwargs)

        return wrapper

    @log_task('Get ssh client', level='debug')
    @_check_alive
    def _get_ssh_client(self):
        ssh_timeout = int(config.get('ssh_timeout'))
        ssh_tries = int(config.get('ssh_tries'))
        start_time = time.time()
        while ssh_tries > 0:
            try:
                LOGGER.debug('still got %d tries' % ssh_tries)
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(paramiko.AutoAddPolicy(), )
                client.connect(
                    self.ip(),
                    username='root',
                    key_filename=self._env.prefix.paths.ssh_id_rsa(),
                    timeout=ssh_timeout,
                )
                return client
            except (socket.error, socket.timeout) as err:
                LOGGER.debug('Socket error: %s', err)
                pass
            except paramiko.ssh_exception.SSHException as err:
                LOGGER.debug('SSH error %s', err)
                pass

            ssh_tries -= 1
            time.sleep(1)

        end_time = time.time()
        raise RuntimeError(
            'Timed out (in %d s) trying to ssh to %s' %
            (end_time - start_time, self.name())
        )

    def ssh(self, command, data=None, show_output=True):
        if not self.alive():
            raise RuntimeError('Attempt to ssh into a not running host')

        client = self._get_ssh_client()
        transport = client.get_transport()
        channel = transport.open_session()

        joined_command = ' '.join(command)
        command_id = _gen_ssh_command_id()
        LOGGER.debug(
            'Running %s on %s: %s%s',
            command_id,
            self.name(),
            joined_command,
            data is not None and (' < "%s"' % data) or '',
        )

        channel.exec_command(joined_command)
        if data is not None:
            channel.send(data)
        channel.shutdown_write()
        rc, out, err = utils.drain_ssh_channel(
            channel, **(
                show_output and {} or {
                    'stdout': None,
                    'stderr': None
                }
            )
        )

        channel.close()
        transport.close()
        client.close()

        LOGGER.debug(
            'Command %s on %s returned with %d',
            command_id,
            self.name(),
            rc,
        )

        if out:
            LOGGER.debug(
                'Command %s on %s output:\n %s',
                command_id,
                self.name(),
                out,
            )
        if err:
            LOGGER.debug(
                'Command %s on %s  errors:\n %s',
                command_id,
                self.name(),
                err,
            )
        return utils.CommandStatus(rc, out, err)

    def wait_for_ssh(self):
        connect_retries = self._spec.get('boot_time_sec', 50)
        while connect_retries:
            ret, _, _ = self.ssh(['true'])
            if ret == 0:
                return
            connect_retries -= 1
            time.sleep(1)
        raise RuntimeError('Failed to connect to remote shell')

    def ssh_script(self, path, show_output=True):
        with open(path) as f:
            return self.ssh(
                ['bash', '-s'],
                data=f.read(),
                show_output=show_output
            )

    @contextlib.contextmanager
    def _scp(self):
        client = self._get_ssh_client()
        scp = SCPClient(client.get_transport())
        try:
            yield scp
        finally:
            client.close()

    def copy_to(self, local_path, remote_path):
        with LogTask(
            'Copy %s to %s:%s' % (local_path, self.name(), remote_path),
        ):
            with self._scp() as scp:
                scp.put(local_path, remote_path)

    def copy_from(self, remote_path, local_path, recursive=True):
        with self._scp() as scp:
            scp.get(
                recursive=recursive,
                remote_path=remote_path,
                local_path=local_path,
            )

    @property
    def metadata(self):
        return self._spec['metadata'].copy()

    def name(self):
        return str(self._spec['name'])

    def iscsi_name(self):
        return 'iqn.2014-07.org.lago:%s' % self.name()

    def ip(self):
        return str(self._env.get_net().resolve(self.name()))

    def _libvirt_name(self):
        return self._env.prefixed_name(self.name())

    def _libvirt_xml(self):
        with open(_path_to_xml('dom_template.xml')) as f:
            dom_raw_xml = f.read()

        qemu_kvm_path = [
            path
            for path in [
                '/usr/libexec/qemu-kvm',
                '/usr/bin/qemu-kvm',
            ] if os.path.exists(path)
        ].pop()

        replacements = {
            '@NAME@': self._libvirt_name(),
            '@VCPU@': self._spec.get('vcpu', 2),
            '@CPU@': self._spec.get('cpu', 2),
            '@MEM_SIZE@': self._spec.get('memory', 16 * 1024),
            '@QEMU_KVM@': qemu_kvm_path,
        }

        for k, v in replacements.items():
            dom_raw_xml = dom_raw_xml.replace(k, str(v), 1)

        dom_xml = lxml.etree.fromstring(dom_raw_xml)
        devices = dom_xml.xpath('/domain/devices')[0]

        disk = devices.xpath('disk')[0]
        devices.remove(disk)

        for disk_order, dev_spec in enumerate(self._spec['disks']):

            # we have to make some adjustments
            # we use iso to indicate cdrom
            # but the ilbvirt wants it named raw
            # and we need to use cdrom device
            disk_device = 'disk'
            bus = 'virtio'
            if dev_spec['format'] == 'iso':
                disk_device = 'cdrom'
                dev_spec['format'] = 'raw'
                bus = 'ide'
            # names converted

            disk = lxml.etree.Element(
                'disk',
                type='file',
                device=disk_device,
            )

            disk.append(
                lxml.etree.Element(
                    'driver',
                    name='qemu',
                    type=dev_spec['format'],
                ),
            )

            disk.append(
                lxml.etree.Element(
                    'boot', order="{}".format(disk_order + 1)
                ),
            )

            disk.append(
                lxml.etree.Element(
                    'source',
                    file=os.path.expandvars(dev_spec['path']),
                ),
            )
            disk.append(
                lxml.etree.Element(
                    'target',
                    dev=dev_spec['dev'],
                    bus=bus,
                ),
            )
            devices.append(disk)

        for dev_spec in self._spec['nics']:
            interface = lxml.etree.Element('interface', type='network', )
            interface.append(
                lxml.etree.Element(
                    'source',
                    network=self._env.prefixed_name(
                        dev_spec['net'], max_length=15
                    ),
                ),
            )
            interface.append(lxml.etree.Element('model', type='virtio', ), )
            if 'ip' in dev_spec:
                interface.append(
                    lxml.etree.Element(
                        'mac', address=_ip_to_mac(dev_spec['ip'])
                    ),
                )
            devices.append(interface)

        return lxml.etree.tostring(dom_xml)

    def start(self):
        if not self.defined():
            with LogTask('Starting VM %s' % self.name()):
                self._env.libvirt_con.createXML(self._libvirt_xml())

    def stop(self):
        if self.defined():
            self._ssh_client = None
            with LogTask('Destroying VM %s' % self.name()):
                self._env.libvirt_con.lookupByName(
                    self._libvirt_name(),
                ).destroy()

    def alive(self):
        return self.state() == 'running'

    def defined(self):
        dom_names = [
            dom.name() for dom in self._env.libvirt_con.listAllDomains()
        ]
        return self._libvirt_name() in dom_names

    def create_snapshot(self, name):
        if self.alive():
            self._create_live_snapshot(name)
        else:
            self._create_dead_snapshot(name)

        self.save()

    def _create_dead_snapshot(self, name):
        raise RuntimeError('Dead snapshots are not implemented yet')

    def _create_live_snapshot(self, name):
        with LogTask(
            'Creating live snapshot named %s for %s' % (name, self.name()),
            level='debug',
        ):

            self.wait_for_ssh()
            self.guest_agent().start()
            self.ssh('sync'.split(' '))

            dom = self._env.libvirt_con.lookupByName(self._libvirt_name())
            dom_xml = lxml.etree.fromstring(dom.XMLDesc())
            disks = dom_xml.xpath('devices/disk')

            with open(_path_to_xml('snapshot_template.xml')) as f:
                snapshot_xml = lxml.etree.fromstring(f.read())
            snapshot_disks = snapshot_xml.xpath('disks')[0]

            for disk in disks:
                target_dev = disk.xpath('target')[0].attrib['dev']
                snapshot_disks.append(
                    lxml.etree.Element(
                        'disk', name=target_dev
                    )
                )

            try:
                dom.snapshotCreateXML(
                    lxml.etree.tostring(snapshot_xml),
                    libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY |
                    libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_QUIESCE,
                )
            except libvirt.libvirtError:
                LOGGER.exception(
                    'Failed to create snapshot %s for %s',
                    name,
                    self.name(),
                )
                raise

            snap_info = []
            new_disks = lxml.etree.fromstring(
                dom.XMLDesc()
            ).xpath('devices/disk')
            for disk, xml_node in zip(self._spec['disks'], new_disks):
                disk['path'] = xml_node.xpath('source')[0].attrib['file']
                disk['format'] = 'qcow2'
                snap_disk = disk.copy()
                snap_disk['path'] = xml_node.xpath(
                    'backingStore',
                )[0].xpath(
                    'source',
                )[0].attrib['file']
                snap_info.append(snap_disk)

            self._reclaim_disks()
            self._spec['snapshots'][name] = snap_info

    def revert_snapshot(self, name):
        try:
            snap_info = self._spec['snapshots'][name]
        except KeyError:
            raise RuntimeError('No snapshot %s for %s' % (name, self.name()))

        with LogTask('Reverting %s to snapshot %s' % (self.name(), name)):

            was_defined = self.defined()
            if was_defined:
                self.stop()
            for disk, disk_template in zip(self._spec['disks'], snap_info):
                os.unlink(os.path.expandvars(disk['path']))
                ret, _, _ = utils.run_command(
                    [
                        'qemu-img',
                        'create',
                        '-f',
                        'qcow2',
                        '-b',
                        disk_template['path'],
                        disk['path'],
                    ],
                    cwd=os.path.dirname(os.path.expandvars(disk['path'])),
                )
                if ret != 0:
                    raise RuntimeError('Failed to revert disk')

            self._reclaim_disks()
            if was_defined:
                self.start()

    def _extract_paths_scp(self, paths):
        for host_path, guest_path in paths:
            LOGGER.debug(
                'Extracting scp://%s:%s to %s',
                self.name(),
                host_path,
                guest_path,
            )
            self.copy_from(local_path=guest_path, remote_path=host_path)

    def _extract_paths_live(self, paths):
        self.guest_agent().start()
        dom = self._env.libvirt_con.lookupByName(self._libvirt_name())
        dom.fsFreeze()
        try:
            self._extract_paths_dead(paths=paths)
        finally:
            dom.fsThaw()

    def _extract_paths_dead(self, paths):
        disk_path = os.path.expandvars(self._spec['disks'][0]['path'])
        disk_root_part = self._spec['disks'][0]['metadata'].get(
            'root-partition',
            'root',
        )

        gfs_cli = guestfs.GuestFS(python_return_dict=True)
        gfs_cli.add_drive_opts(disk_path, format='qcow2', readonly=1)
        gfs_cli.set_backend('direct')
        gfs_cli.launch()
        rootfs = [
            filesystem
            for filesystem in gfs_cli.list_filesystems()
            if disk_root_part in filesystem
        ]
        if not rootfs:
            raise RuntimeError(
                'No root fs (%s) could be found for %s form list %s' %
                (disk_root_part, disk_path, str(gfs_cli.list_filesystems()))
            )
        else:
            rootfs = rootfs[0]
        gfs_cli.mount_ro(rootfs, '/')
        for (guest_path, host_path) in paths:
            LOGGER.debug(
                'Extracting guestfs://%s:%s to %s',
                self.name(),
                host_path,
                guest_path,
            )
            try:
                _guestfs_copy_path(gfs_cli, guest_path, host_path)
            except Exception:
                LOGGER.exception(
                    'Failed to copy %s from %s',
                    guest_path,
                    self.name(),
                )
        gfs_cli.shutdown()
        gfs_cli.close()

    def has_guest_agent(self):
        try:
            self.guest_agent()
        except RuntimeError:
            return False

        return True

    def ssh_reachable(self):
        try:
            self._get_ssh_client()
        except RuntimeError:
            return False

        return True

    def extract_paths(self, paths):
        if self.alive() and self.ssh_reachable() and self.has_guest_agent():
            self._extract_paths_live(paths=paths)
        elif self.alive() and self.ssh_reachable():
            self._extract_paths_scp(paths=paths)
        elif self.alive():
            raise RuntimeError(
                'Unable to extract logs from alive but unreachable host %s. '
                'Try stopping it first' % self.name()
            )
        else:
            self._extract_paths_dead(paths=paths)

    def save(self, path=None):
        if path is None:
            path = self._env.virt_path('vm-%s' % self.name())
        with open(path, 'w') as f:
            utils.json_dump(self._spec, f)

    def bootstrap(self):
        with LogTask('Bootstrapping %s' % self.name()):
            if self._spec['disks'][0]['type'] != 'empty' and self._spec[
                'disks'
            ][0]['format'] != 'iso':
                sysprep.sysprep(
                    self._spec['disks'][0]['path'],
                    [
                        sysprep.set_hostname(self.name()),
                        sysprep.set_root_password(self.root_password()),
                        sysprep.add_ssh_key(
                            self._env.prefix.paths.ssh_id_rsa_pub(),
                            with_restorecon_fix=(self.distro() == 'fc23'),
                        ),
                        sysprep.set_iscsi_initiator_name(self.iscsi_name()),
                        sysprep.set_selinux_mode('enforcing'),
                    ] + [
                        sysprep.config_net_interface_dhcp(
                            'eth%d' % index,
                            _ip_to_mac(nic['ip']),
                        )
                        for index, nic in enumerate(self._spec['nics'])
                        if 'ip' in nic
                    ],
                )

    def _reclaim_disk(self, path):
        if pwd.getpwuid(os.stat(path).st_uid).pw_name == 'qemu':
            utils.run_command(['sudo', '-u', 'qemu', 'chmod', 'a+rw', path])
        else:
            os.chmod(path, 0666)

    def _reclaim_disks(self):
        for disk in self._spec['disks']:
            self._reclaim_disk(disk['path'])

    @_check_defined
    def vnc_port(self):
        dom = self._env.libvirt_con.lookupByName(self._libvirt_name())
        dom_xml = lxml.etree.fromstring(dom.XMLDesc())
        return dom_xml.xpath('devices/graphics').pop().attrib['port']

    def _detect_service_manager(self):
        LOGGER.debug('Detecting service manager for %s', self.name())
        for manager_name, service_class in _SERVICE_WRAPPERS.items():
            if service_class.is_supported(self):
                LOGGER.debug(
                    'Setting %s as service manager for %s',
                    manager_name,
                    self.name(),
                )
                self._service_class = service_class
                self._spec['service_class'] = manager_name
                self.save()
                return

        raise RuntimeError('No service manager detected for %s' % self.name())

    @_check_alive
    def service(self, name):
        if self._service_class is None:
            self._detect_service_manager()

        return self._service_class(self, name)

    def guest_agent(self):
        if 'guest-agent' not in self._spec:
            for possible_name in ('qemu-ga', 'qemu-guest-agent'):
                try:
                    if self.service(possible_name).exists():
                        self._spec['guest-agent'] = possible_name
                        self.save()
                        break
                except RuntimeError as err:
                    raise RuntimeError(
                        'Could not find guest agent service: %s' % err
                    )
            else:
                raise RuntimeError('Could not find guest agent service')

        return self.service(self._spec['guest-agent'])

    @_check_alive
    def interactive_ssh(self, command):
        client = self._get_ssh_client()
        transport = client.get_transport()
        channel = transport.open_session()
        try:
            return utils.interactive_ssh_channel(channel, ' '.join(command))
        finally:
            channel.close()
            transport.close()
            client.close()

    @_check_defined
    def interactive_console(self):
        """
        Opens an interactive console

        Returns:
            lago.utils.CommandStatus: result of the virsh command execution
        """
        virsh_command = [
            "virsh",
            "-c",
            LIBVIRT_URL,
            "console",
            self._libvirt_name(),
        ]
        return utils.run_interactive_command(command=virsh_command, )

    def nics(self):
        return self._spec['nics'][:]

    def nets(self):
        return [nic['net'] for nic in self._spec['nics']]

    def _template_metadata(self):
        return self._spec['disks'][0].get('metadata', {})

    def distro(self):
        return self._template_metadata().get('distro', None)

    def root_password(self):
        return self._spec['root-password']

    def state(self):
        """
        Return a small description of the current status of the domain

        Returns:
            str: small description of the domain status, 'down' if it's not
            defined at all.
        """
        if not self.defined():
            return 'down'

        state = self._env.libvirt_con.lookupByName(
            self._libvirt_name()
        ).state()
        return libvirt_utils.Domain.resolve_state(state)

    def _artifact_paths(self):
        return self._spec.get('artifacts', [])

    def collect_artifacts(self, host_path):
        self.extract_paths(
            [
                (
                    guest_path,
                    os.path.join(host_path, guest_path.replace('/', '_')),
                ) for guest_path in self._artifact_paths()
            ]
        )
