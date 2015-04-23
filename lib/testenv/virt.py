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
import functools
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

import utils

HOSTNAME_PATH = '/etc/hostname'
ISCSI_DIR = '/etc/iscsi/'
ISCSI_INITIATOR_NAME_PATH = os.path.join(ISCSI_DIR, 'initiatorname.iscsi')

SSH_DIR = '/root/.ssh/'
AUTHORIZED_KEYS = os.path.join(SSH_DIR, 'authorized_keys')
PERSISTENT_NET_RULES = '/etc/udev/rules.d/70-persistent-net.rules'


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
                    host_path,
                    os.path.basename(path)
                ),
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

    * libvirt_con
    '''
    def __init__(self, prefix, vm_specs, net_specs):
        self.prefix = prefix

        with open(self._prefix.paths.uuid(), 'r') as f:
            self._uuid = f.read().strip()

        self._nets = {}
        for name, spec in net_specs.items():
            self._nets[name] = self._create_net(spec)

        self._vms = {}
        for name, spec in vm_specs.items():
            self._vms[name] = self._create_vm(spec)

        self._libvirt_con = None

    def _create_net(self, net_spec):
        return Network(self, net_spec)

    def _create_vm(self, vm_spec):
        return VM(self, vm_spec)

    def prefixed_name(self, unprefixed_name):
        return '%s-%s' % (self._uuid[:8], unprefixed_name)

    def virt_path(self, *args):
        return self._prefix.paths.virt(*args)

    def bootstrap(self):
        vec = [vm.bootstrap for vm in self._vms.values()]
        vt = utils.VectorThread(vec)
        vt.start_all()
        vt.join_all()

    @property
    def libvirt_con(self):
        if self._libvirt_con is None:
            self._libvirt_con = libvirt.open('qemu:///system')
        return self._libvirt_con

    def start(self):
        with utils.RollbackContext() as rollback:
            for net in self._nets.values():
                net.start()
                rollback.prependDefer(net.stop)

            for vm in self._vms.values():
                vm.start()
                rollback.prependDefer(vm.stop)
            rollback.clear()

    def stop(self):
        for vm in self._vms.values():
            vm.stop()
        for net in self._nets.values():
            net.stop()

    def get_nets(self):
        return self._nets.copy()

    def get_net(self, name=None):
        if name:
            return self.get_nets().get(name)
        else:
            return [
                net
                for net in self.get_nets().values()
                if net.is_management()
            ].pop()

    def get_vms(self):
        return self._vms.copy()

    def get_vm(self, name):
        return self._vms[name]

    @classmethod
    def from_prefix(clazz, prefix):
        virt_path = lambda name: \
            os.path.join(prefix.paths.prefix(), 'virt', name)
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

        return clazz(prefix, vm_specs, net_specs)

    def save(self):
        for net in self._nets.values():
            net.save()
        for vm in self._vms.values():
            vm.save()

        spec = {
            'nets': self._nets.keys(),
            'vms': self._vms.keys(),
        }

        with open(self.virt_path('env'), 'w') as f:
            utils.json_dump(spec, f)

    def create_snapshots(self, name):
        vec = [
            functools.partial(vm.create_snapshot, name)
            for vm in self._vms.values()
        ]
        vt = utils.VectorThread(vec)
        vt.start_all()
        vt.join_all()

    def revert_snapshots(self, name):
        vec = [
            functools.partial(vm.revert_snapshot, name)
            for vm in self._vms.values()
        ]
        vt = utils.VectorThread(vec)
        vt.start_all()
        vt.join_all()


class Network(object):
    def __init__(self, env, spec):
        self._env = env
        self._spec = spec

    def name(self):
        return self._spec['name']

    def gw(self):
        return self._spec['gw']

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
        return self._env.prefixed_name(self.name())

    def _libvirt_xml(self):
        with open(_path_to_xml('net_template.xml')) as f:
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
                return '.'.join(
                    self.gw().split('.')[:-1] + [str(last)]
                )

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

    def alive(self):
        net_names = [
            net.name()
            for net in self._env.libvirt_con.listAllNetworks()
        ]
        return self._libvirt_name() in net_names

    def start(self):
        if not self.alive():
            logging.info('Creating network %s', self.name())
            self._env.libvirt_con.networkCreateXML(self._libvirt_xml())

    def stop(self):
        if self.alive():
            logging.info('Destroying network %s', self.name())
            self._env.libvirt_con.networkLookupByName(
                self._libvirt_name(),
            ).destroy()

    def save(self):
        with open(self._env.virt_path('net-%s' % self.name()), 'w') as f:
            utils.json_dump(self._spec, f)


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


class _SystemdService(_Service):
    BIN_PATH = '/usr/bin/systemctl'

    def _request_start(self):
        return self._vm.ssh([self.BIN_PATH, 'start', self._name])[0]

    def _request_stop(self):
        return self._vm.ssh([self.BIN_PATH, 'stop', self._name])[0]

    def state(self):
        ret, out, _ = self._vm.ssh([self.BIN_PATH, 'status', self._name])
        if ret == 0:
            return ServiceState.ACTIVE

        lines = [l.strip() for l in out.split('\n')]
        loaded = [l for l in lines if l.startswith('Loaded:')].pop()

        if loaded.split()[1] == 'loaded':
            return ServiceState.INACTIVE

        return ServiceState.MISSING


class _SysVInitService(_Service):
    BIN_PATH = '/sbin/service'

    def _request_start(self):
        return self._vm.ssh([self.BIN_PATH, self._name, 'start'])[0]

    def _request_stop(self):
        return self._vm.ssh([self.BIN_PATH, self._name, 'stop'])[0]

    def state(self):
        ret, out, _ = self._vm.ssh([self.BIN_PATH, self._name, 'status'])
        if ret == 0:
            return ServiceState.ACTIVE

        if out.strip().endswith('is stopped'):
            return ServiceState.INACTIVE

        return ServiceState.MISSING

_SERVICE_WRAPPERS = collections.OrderedDict()
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
    def _normalize_spec(clazz, spec):
        spec['snapshots'] = spec.get('snapshots', {})
        spec['metadata'] = spec.get('metadata', {})
        return spec

    def _open_ssh_client(self):
        while self._ssh_client is None:
            try:
                client = paramiko.SSHClient()
                client.set_missing_host_key_policy(
                    paramiko.AutoAddPolicy(),
                )
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

    def _check_alive(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if not self.alive():
                raise RuntimeError('VM is not running')
            return func(self, *args, **kwargs)
        return wrapper

    @_check_alive
    def _get_ssh_client(self):
        if self._ssh_client is None:
            self._ssh_client = self._open_ssh_client()
        return self._ssh_client

    def ssh(self, command, data=None, show_output=True):
        if not self.alive():
            raise RuntimeError('Attempt to ssh into offline host')

        channel = self._get_ssh_client().get_transport().open_session()

        joined_command = ' '.join(command)
        command_id = _gen_ssh_command_id()
        logging.debug(
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
        out, err = utils.drain_ssh_channel(
            channel,
            **(show_output and {} or {'stdout': None, 'stderr': None})
        )
        rc = channel.exit_status

        logging.debug(
            'Command %s on %s returned with %d',
            command_id,
            self.name(),
            rc,
        )

        if out:
            logging.debug(
                'Command %s on %s output:\n %s',
                command_id,
                self.name(),
                out,
            )
        if err:
            logging.debug(
                'Command %s on %s  errors:\n %s',
                command_id,
                self.name(),
                err,
            )
        return rc, out, err

    def wait_for_ssh(self, connect_retries=50):
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

    def scp_to(self, local_path, remote_path, remote_user='root'):
        sftp = self._get_ssh_client().open_sftp()
        try:
            sftp.put(local_path, remote_path)
        finally:
            sftp.close()

    def scp_from(self, remote_path, local_path, remote_user='root'):
        sftp = self._get_ssh_client().open_sftp()
        try:
            sftp.get(remote_path, local_path)
        finally:
            sftp.close()

    @property
    def metadata(self):
        return self._spec['metadata'].copy()

    def name(self):
        return str(self._spec['name'])

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
            '@VCPU@': self._spec.get('vcpu', 4),
            '@CPU@': self._spec.get('cpu', 4),
            '@MEM_SIZE@': self._spec.get('memory', 16 * 1024),
            '@QEMU_KVM@': qemu_kvm_path,
        }

        for k, v in replacements.items():
            dom_raw_xml = dom_raw_xml.replace(k, str(v), 1)

        dom_xml = lxml.etree.fromstring(dom_raw_xml)
        devices = dom_xml.xpath('/domain/devices')[0]

        disk = devices.xpath('disk')[0]
        devices.remove(disk)

        for dev_spec in self._spec['disks']:
            disk = lxml.etree.Element(
                'disk',
                type='file',
                device='disk',
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
                    'source',
                    file=dev_spec['path'],
                ),
            )
            disk.append(
                lxml.etree.Element(
                    'target',
                    dev=dev_spec['dev'],
                    bus='virtio',
                ),
            )
            devices.append(disk)

        for dev_spec in self._spec['nics']:
            interface = lxml.etree.Element(
                'interface',
                type='network',
            )
            interface.append(
                lxml.etree.Element(
                    'source',
                    network=self._env.prefixed_name(dev_spec['net']),
                ),
            )
            interface.append(
                lxml.etree.Element(
                    'model',
                    type='virtio',
                ),
            )
            interface.append(
                lxml.etree.Element(
                    'mac',
                    address=_ip_to_mac(dev_spec['ip'])
                ),
            )
            devices.append(interface)

        return lxml.etree.tostring(dom_xml)

    def start(self):
        if not self.alive():
            logging.info('Starting VM %s', self.name())
            self._env.libvirt_con.createXML(self._libvirt_xml())

    def stop(self):
        if self.alive():
            self._ssh_client = None
            logging.info('Destroying VM %s', self.name())
            self._env.libvirt_con.lookupByName(
                self._libvirt_name(),
            ).destroy()

    def alive(self):
        dom_names = [
            dom.name()
            for dom in self._env.libvirt_con.listAllDomains()
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
        logging.info(
            'Creating live snapshot named %s for %s',
            name,
            self.name(),
        )

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
            snapshot_disks.append(lxml.etree.Element('disk', name=target_dev))

        try:
            dom.snapshotCreateXML(
                lxml.etree.tostring(snapshot_xml),
                libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY |
                libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_QUIESCE,
            )
        except libvirt.libvirtError:
            logging.exception(
                'Failed to create snapshot %s for %s', name, self.name(),
            )
            raise

        snap_info = []
        new_disks = lxml.etree.fromstring(dom.XMLDesc()).xpath('devices/disk')
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

        logging.info('Reverting %s to snapshot %s', self.name(), name)

        was_alive = self.alive()
        if was_alive:
            self.stop()
        for disk, disk_template in zip(self._spec['disks'], snap_info):
            os.unlink(disk['path'])
            ret, _, _ = utils.run_command(
                [
                    'qemu-img',
                    'create',
                    '-f', 'qcow2',
                    '-b', disk_template['path'],
                    disk['path'],
                ],
                cwd=os.path.dirname(disk['path']),
            )
            if ret != 0:
                raise RuntimeError('Failed to revert disk')

        self._reclaim_disks()
        if was_alive:
            self.start()

    def extract_paths(self, paths):
        self.guest_agent().start()
        dom = self._env.libvirt_con.lookupByName(self._libvirt_name())
        dom.fsFreeze()
        try:
            disk_path = self._spec['disks'][0]['path']
            g = guestfs.GuestFS(python_return_dict=True)
            g.add_drive_opts(disk_path, format='qcow2', readonly=1)
            g.set_backend('direct')
            g.launch()
            rootfs = filter(lambda x: 'root' in x, g.list_filesystems())[0]
            g.mount_ro(rootfs, '/')
            for (guest_path, host_path) in paths:
                try:
                    _guestfs_copy_path(g, guest_path, host_path)
                except Exception:
                    logging.exception(
                        'Failed to copy %s from %s', guest_path, self.name(),
                    )
            g.shutdown()
            g.close()
        finally:
            dom.fsThaw()

    def save(self, path=None):
        if path is None:
            path = self._env.virt_path('vm-%s' % self.name())
        with open(path, 'w') as f:
            utils.json_dump(self._spec, f)

    def bootstrap(self):
        path = self._spec['disks'][0]['path']
        logging.debug('Bootstrapping %s:%s begin', self.name(), path)

        g = guestfs.GuestFS(python_return_dict=True)
        g.add_drive_opts(path, format='qcow2', readonly=0)
        g.set_backend('direct')
        g.launch()
        try:
            rootfs = filter(lambda x: 'root' in x, g.list_filesystems())[0]
            g.mount(rootfs, '/')

            # /etc/hostname
            g.write(HOSTNAME_PATH, self.name() + '\n')

            # /etc/iscsi/initiatorname.iscsi
            if not g.exists(ISCSI_DIR):
                g.mkdir(ISCSI_DIR)
            g.write(
                ISCSI_INITIATOR_NAME_PATH,
                'InitiatorName=iqn.2014-07.org.ovirt:%s\n' % self.name(),
            )

            # $HOME/.ssh/authorized_keys
            if not g.exists(SSH_DIR):
                g.mkdir(SSH_DIR)
                g.chmod(0700, SSH_DIR)
            with open(self._env.prefix.paths.ssh_id_rsa_pub()) as f:
                g.write(AUTHORIZED_KEYS, f.read())

            # persistent net rules
            if g.exists(PERSISTENT_NET_RULES):
                g.rm(PERSISTENT_NET_RULES)

            logging.debug('Bootstrapping %s:%s end', self.name(), path)
        finally:
            g.shutdown()
            g.close()

    def _reclaim_disk(self, path):
        if pwd.getpwuid(os.stat(path).st_uid).pw_name == 'qemu':
            utils.run_command(['sudo', '-u', 'qemu', 'chmod', 'a+rw', path])
        else:
            os.chmod(path, 0666)

    def _reclaim_disks(self):
        for disk in self._spec['disks']:
            self._reclaim_disk(disk['path'])

    @_check_alive
    def vnc_port(self):
        dom = self._env.libvirt_con.lookupByName(self._libvirt_name())
        dom_xml = lxml.etree.fromstring(dom.XMLDesc())
        return dom_xml.xpath('devices/graphics').pop().attrib['port']

    @_check_alive
    def service(self, name):
        if self._service_class is None:
            logging.debug('Detecting service manager for %s', self.name())
            for manager_name, service_class in _SERVICE_WRAPPERS.items():
                ret, _, _ = self.ssh(['test', '-e', service_class.BIN_PATH])
                if not ret:
                    logging.debug(
                        'Setting %s as service manager for %s',
                        manager_name,
                        self.name(),
                    )
                    self._service_class = service_class
                    self._spec['service_class'] = manager_name
                    self.save()
                    break

        return self._service_class(self, name)

    def guest_agent(self):
        if 'guest-agent' not in self._spec:
            for possible_name in ('qemu-ga', 'qemu-guest-agent'):
                if self.service(possible_name).exists():
                    self._spec['guest-agent'] = possible_name
                    self.save()
                    break
            else:
                raise RuntimeError('Could not find guest agent service')
        return self.service(self._spec['guest-agent'])

    @_check_alive
    def interactive_ssh(self, command):
        channel = self._get_ssh_client().get_transport().open_session()
        utils.interactive_ssh_channel(channel, ' '.join(command))

    def nics(self):
        return self._spec['nics'][:]

    def _template_metadata(self):
        return self._spec['disks'][0].get('metadata', {})

    def distro(self):
        return self._template_metadata().get('distro', None)

    def root_password(self):
        return self._template_metadata()['root-password']
