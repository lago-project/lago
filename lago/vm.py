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
import guestfs
import libvirt
import logging
import lxml
import os
import pwd

from . import (log_utils, utils, sysprep, libvirt_utils, config, )
from .plugins import vm

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


def _path_to_xml(basename):
    return os.path.join(os.path.dirname(__file__), basename, )


def _check_defined(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.defined():
            raise RuntimeError('VM %s is not defined' % self.vm.name())
        return func(self, *args, **kwargs)

    return wrapper


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

    def create_snapshot(self, name, *args, **kwargs):
        pass

    def revert_snapshot(self, name, *args, **kwargs):
        pass

    def vnc_port(self, *args, **kwargs):
        return 'no-vnc'


class LocalLibvirtVMProvider(vm.VMProviderPlugin):
    def __init__(self, vm):
        super(LocalLibvirtVMProvider, self).__init__(vm)
        libvirt_url = config.get('libvirt_url')
        self.libvirt_con = libvirt_utils.get_libvirt_connection(
            name=self.vm.virt_env.uuid + libvirt_url,
            libvirt_url=libvirt_url,
        )

    def start(self):
        super(LocalLibvirtVMProvider, self).start()
        if not self.defined():
            with LogTask('Starting VM %s' % self.vm.name()):
                self.libvirt_con.createXML(self._libvirt_xml())

    def stop(self):
        super(LocalLibvirtVMProvider, self).stop()
        if self.defined():
            self.vm._ssh_client = None
            with LogTask('Destroying VM %s' % self.vm.name()):
                self.libvirt_con.lookupByName(self._libvirt_name(), ).destroy()

    def defined(self):
        dom_names = [dom.name() for dom in self.libvirt_con.listAllDomains()]
        return self._libvirt_name() in dom_names

    def bootstrap(self):
        with LogTask('Bootstrapping %s' % self.vm.name()):
            if self.vm._spec['disks'][0]['type'] != 'empty' and self.vm._spec[
                'disks'
            ][0]['format'] != 'iso':
                sysprep.sysprep(
                    self.vm._spec['disks'][0]['path'],
                    [
                        sysprep.set_hostname(self.vm.name()),
                        sysprep.set_root_password(self.vm.root_password()),
                        sysprep.add_ssh_key(
                            self.vm.virt_env.prefix.paths.ssh_id_rsa_pub(),
                            with_restorecon_fix=(self.vm.distro() == 'fc23'),
                        ),
                        sysprep.set_iscsi_initiator_name(self.vm.iscsi_name()),
                        sysprep.set_selinux_mode('enforcing'),
                    ] + [
                        sysprep.config_net_interface_dhcp(
                            'eth%d' % index,
                            utils.ip_to_mac(nic['ip']),
                        )
                        for index, nic in enumerate(self.vm._spec['nics'])
                        if 'ip' in nic
                    ],
                )

    def state(self):
        """
        Return a small description of the current status of the domain

        Returns:
            str: small description of the domain status, 'down' if it's not
            defined at all.
        """
        if not self.defined():
            return 'down'

        state = self.libvirt_con.lookupByName(self._libvirt_name()).state()
        return libvirt_utils.Domain.resolve_state(state)

    def create_snapshot(self, name):
        if self.vm.alive():
            self._create_live_snapshot(name)
        else:
            self._create_dead_snapshot(name)

        self.vm.save()

    def revert_snapshot(self, name):
        try:
            snap_info = self.vm._spec['snapshots'][name]
        except KeyError:
            raise RuntimeError(
                'No snapshot %s for %s' % (name, self.vm.name())
            )

        with LogTask('Reverting %s to snapshot %s' % (self.vm.name(), name)):

            was_defined = self.defined()
            if was_defined:
                self.stop()
            for disk, disk_template in zip(self.vm._spec['disks'], snap_info):
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

    def extract_paths(self, paths):
        if (
            self.vm.alive() and self.vm.ssh_reachable()
            and self.vm.has_guest_agent()
        ):
            self._extract_paths_live(paths=paths)
        elif not self.vm.alive():
            self._extract_paths_dead(paths=paths)
        else:
            super(LocalLibvirtVMProvider, self).extract_paths(paths=paths)

    @_check_defined
    def vnc_port(self):
        dom = self.libvirt_con.lookupByName(self._libvirt_name())
        dom_xml = lxml.etree.fromstring(dom.XMLDesc())
        return dom_xml.xpath('devices/graphics').pop().attrib['port']

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
            config.get('libvirt_url'),
            "console",
            self._libvirt_name(),
        ]
        return utils.run_interactive_command(command=virsh_command, )

    def _libvirt_name(self):
        return self.vm.virt_env.prefixed_name(self.vm.name())

    def _libvirt_xml(self):
        with open(_path_to_xml('dom_template.xml')) as xml_fd:
            dom_raw_xml = xml_fd.read()

        qemu_kvm_path = [
            path
            for path in [
                '/usr/libexec/qemu-kvm',
                '/usr/bin/qemu-kvm',
            ] if os.path.exists(path)
        ].pop()

        replacements = {
            '@NAME@': self._libvirt_name(),
            '@VCPU@': self.vm._spec.get('vcpu', 2),
            '@CPU@': self.vm._spec.get('cpu', 2),
            '@MEM_SIZE@': self.vm._spec.get('memory', 16 * 1024),
            '@QEMU_KVM@': qemu_kvm_path,
        }

        for key, val in replacements.items():
            dom_raw_xml = dom_raw_xml.replace(key, str(val), 1)

        dom_xml = lxml.etree.fromstring(dom_raw_xml)
        devices = dom_xml.xpath('/domain/devices')[0]

        disk = devices.xpath('disk')[0]
        devices.remove(disk)

        for disk_order, dev_spec in enumerate(self.vm._spec['disks']):

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

        for dev_spec in self.vm._spec['nics']:
            interface = lxml.etree.Element('interface', type='network', )
            interface.append(
                lxml.etree.Element(
                    'source',
                    network=self.vm.virt_env.prefixed_name(
                        dev_spec['net'], max_length=15
                    ),
                ),
            )
            interface.append(lxml.etree.Element('model', type='virtio', ), )
            if 'ip' in dev_spec:
                interface.append(
                    lxml.etree.Element(
                        'mac', address=utils.ip_to_mac(dev_spec['ip'])
                    ),
                )
            devices.append(interface)

        return lxml.etree.tostring(dom_xml)

    def _create_dead_snapshot(self, name):
        raise RuntimeError('Dead snapshots are not implemented yet')

    def _create_live_snapshot(self, name):
        with LogTask(
            'Creating live snapshot named %s for %s' % (name, self.vm.name()),
            level='debug',
        ):

            self.vm.wait_for_ssh()
            self.vm.guest_agent().start()
            self.vm.ssh('sync'.split(' '))

            dom = self.libvirt_con.lookupByName(self._libvirt_name())
            dom_xml = lxml.etree.fromstring(dom.XMLDesc())
            disks = dom_xml.xpath('devices/disk')

            with open(_path_to_xml('snapshot_template.xml')) as xml_fd:
                snapshot_xml = lxml.etree.fromstring(xml_fd.read())
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
                    self.vm.name(),
                )
                raise

            snap_info = []
            new_disks = lxml.etree.fromstring(
                dom.XMLDesc()
            ).xpath('devices/disk')
            for disk, xml_node in zip(self.vm._spec['disks'], new_disks):
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
            self.vm._spec['snapshots'][name] = snap_info

    def _extract_paths_live(self, paths):
        self.vm.guest_agent().start()
        dom = self.libvirt_con.lookupByName(self._libvirt_name())
        dom.fsFreeze()
        try:
            self._extract_paths_dead(paths=paths)
        finally:
            dom.fsThaw()

    def _extract_paths_dead(self, paths):
        disk_path = os.path.expandvars(self.vm._spec['disks'][0]['path'])
        disk_root_part = self.vm._spec['disks'][0]['metadata'].get(
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
                self.vm.name(),
                host_path,
                guest_path,
            )
            try:
                _guestfs_copy_path(gfs_cli, guest_path, host_path)
            except Exception:
                LOGGER.exception(
                    'Failed to copy %s from %s',
                    guest_path,
                    self.vm.name(),
                )
        gfs_cli.shutdown()
        gfs_cli.close()

    def _reclaim_disk(self, path):
        if pwd.getpwuid(os.stat(path).st_uid).pw_name == 'qemu':
            utils.run_command(['sudo', '-u', 'qemu', 'chmod', 'a+rw', path])
        else:
            os.chmod(path, 0666)

    def _reclaim_disks(self):
        for disk in self.vm._spec['disks']:
            self._reclaim_disk(disk['path'])


def _guestfs_copy_path(guestfs_conn, guest_path, host_path):
    if guestfs_conn.is_file(guest_path):
        with open(host_path, 'w') as dest_fd:
            dest_fd.write(guestfs_conn.read_file(guest_path))

    elif guestfs_conn.is_dir(guest_path):
        os.mkdir(host_path)
        for path in guestfs_conn.ls(guest_path):
            _guestfs_copy_path(
                guestfs_conn,
                os.path.join(
                    guest_path,
                    path,
                ),
                os.path.join(
                    host_path, os.path.basename(path)
                ),
            )
