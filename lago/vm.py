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
import time
import guestfs
import libvirt
import logging
import lxml
import os
import pwd

from . import (log_utils, utils, sysprep, libvirt_utils, export)
from .config import config
from .plugins import vm
from .plugins.vm import ExtractPathError, ExtractPathNoPathError

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


def _path_to_xml(basename):
    return os.path.join(
        os.path.dirname(__file__),
        basename,
    )


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


class LocalLibvirtVMProvider(vm.VMProviderPlugin):
    def __init__(self, vm):
        super(LocalLibvirtVMProvider, self).__init__(vm)
        libvirt_url = config.get('libvirt_url')
        self.libvirt_con = libvirt_utils.get_libvirt_connection(
            name=self.vm.virt_env.uuid + libvirt_url,
            libvirt_url=libvirt_url,
        )
        self._cpu_model = self.vm._spec.get(
            'cpu_model', self.vm.virt_env.get_compatible_cpu_and_family()[0]
        )

    def start(self):
        super(LocalLibvirtVMProvider, self).start()
        if not self.defined():
            # the wait_suspend method is a work around for:
            # https://bugzilla.redhat.com/show_bug.cgi?id=1411025
            # 'LAGO__START_WAIT__SUSPEND' should be set to a float or integer
            # indicating how much time to sleep between the time the domain
            # is created in paused mode, until it is resumed.
            wait_suspend = os.environ.get('LAGO__START__WAIT_SUSPEND')
            with LogTask('Starting VM %s' % self.vm.name()):
                if wait_suspend is None:
                    dom = self.libvirt_con.createXML(self._libvirt_xml())
                    if not dom:
                        raise RuntimeError(
                            'Failed to create Domain: %s' % self._libvirt_xml()
                        )
                else:
                    LOGGER.debug('starting domain in paused mode')
                    try:
                        wait_suspend = float(wait_suspend)
                    except:
                        raise ValueError(
                            'LAGO__START__WAIT_SUSPEND value is not a number'
                        )
                    dom = self.libvirt_con.createXML(
                        self._libvirt_xml(),
                        flags=libvirt.VIR_DOMAIN_START_PAUSED
                    )
                    time.sleep(wait_suspend)
                    dom.resume()
                    if not dom.isActive():
                        raise RuntimeError(
                            'failed to resume %s domain' % dom.name()
                        )

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
                        ),
                        sysprep.set_iscsi_initiator_name(self.vm.iscsi_name()),
                        sysprep.edit(
                            "/boot/grub2/grub.cfg",
                            "s/set timeout=5/set timeout=0/g"
                        ) if (
                            self.vm.distro() == 'el7' or self.vm.distro() ==
                            'fc24'
                        ) else '',
                    ] + [
                        sysprep.config_net_interface_dhcp(
                            'eth%d' % index,
                            utils.ipv4_to_mac(nic['ip']),
                        ) for index, nic in enumerate(self.vm._spec['nics'])
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

    def extract_paths(self, paths, ignore_nopath):
        """
        Extract the given paths from the domain

        Attempt to extract all files defined in ``paths`` with the method
        defined in :func:`~lago.plugins.vm.VMProviderPlugin.extract_paths`,
        if it fails, will try extracting the files with libguestfs.

        Args:
            paths(list of str): paths to extract
            ignore_nopath(boolean): if True will ignore none existing paths.

        Returns:
            None

        Raises:
            :exc:`~lago.plugins.vm.ExtractPathNoPathError`: if a none existing
                path was found on the VM, and `ignore_nopath` is True.
            :exc:`~lago.plugins.vm.ExtractPathError`: on all other failures.
        """

        try:

            super(LocalLibvirtVMProvider, self).extract_paths(
                paths=paths,
                ignore_nopath=ignore_nopath,
            )
        except ExtractPathError as err:
            LOGGER.debug(
                '%s: failed extracting files: %s', self.vm.name(), err.message
            )
            LOGGER.debug(
                '%s: attempting to extract files with libguestfs',
                self.vm.name()
            )
            self._extract_paths_gfs(paths=paths, ignore_nopath=ignore_nopath)

    def export_disks(self, standalone, dst_dir, compress, *args, **kwargs):
        """
        Exports all the disks of self.
        For each disk type, handler function should be added.

        Args:
            standalone (bool): if true, merge the base images and the layered
             image into a new file (Supported only in qcow2 format)
            dst_dir (str): dir to place the exported disks
            compress(bool): if true, compress each disk.

        """
        if not os.path.isdir(dst_dir):
            os.mkdir(dst_dir)

        export_managers = [
            export.DiskExportManager.get_instance_by_type(
                dst=dst_dir,
                disk=disk,
                do_compress=compress,
                standalone=standalone,
                *args,
                **kwargs
            ) for disk in self.vm.disks
        ]

        # TODO: make this step parallel
        for manager in export_managers:
            manager.export()

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

    @property
    def cpu_model(self):
        """
        Return the VM CPU model for domain XML generation

        Returns:
            str: cpu model
        """
        return self._cpu_model

    def _libvirt_name(self):
        return self.vm.virt_env.prefixed_name(self.vm.name())

    def _libvirt_xml(self):
        with open(_path_to_xml('dom_template.xml')) as xml_fd:
            dom_raw_xml = xml_fd.read()

        capabilities_raw_xml = self.libvirt_con.getCapabilities()
        capabilities_xml = lxml.etree.fromstring(capabilities_raw_xml)
        qemu_kvm_path = capabilities_xml.findtext(
            "guest[os_type='hvm']/arch[@name='x86_64']/domain[@type='kvm']"
            "/emulator"
        )

        if not qemu_kvm_path:
            LOGGER.warning("hardware acceleration not available")
            qemu_kvm_path = capabilities_xml.findtext(
                "guest[os_type='hvm']/arch[@name='x86_64']"
                "/domain[@type='qemu']/../emulator"
            )

        if not qemu_kvm_path:
            raise Exception('kvm executable not found')

        replacements = {
            '@NAME@': self._libvirt_name(),
            '@VCPU@': self.vm._spec.get('vcpu', 2),
            '@CPU@': self.vm._spec.get('cpu', 2),
            '@CPUMODEL@': self.cpu_model,
            '@MEM_SIZE@': self.vm._spec.get('memory', 16 * 1024),
            '@QEMU_KVM@': qemu_kvm_path,
        }

        for key, val in replacements.items():
            dom_raw_xml = dom_raw_xml.replace(key, str(val), 1)

        dom_xml = lxml.etree.fromstring(dom_raw_xml)
        devices = dom_xml.xpath('/domain/devices')[0]

        disk = devices.xpath('disk')[0]
        devices.remove(disk)

        scsi_con_exists = False
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

            # support virtio-scsi - sdX devices
            if dev_spec['dev'].startswith('sd'):
                bus = 'scsi'
                if not scsi_con_exists:
                    controller = lxml.etree.Element(
                        'controller',
                        type='scsi',
                        index='0',
                        model='virtio-scsi',
                    )
                    driver = lxml.etree.Element(
                        'driver',
                        iothread='1',
                    )
                    controller.append(driver)
                    devices.append(controller)
                    scsi_con_exists = True

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
                    discard='unmap',
                ),
            )

            serial = lxml.etree.SubElement(disk, 'serial')
            serial.text = "{}".format(disk_order + 1)
            disk.append(serial)

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
            interface = lxml.etree.Element(
                'interface',
                type='network',
            )
            interface.append(
                lxml.etree.Element(
                    'source',
                    network=self.vm.virt_env.prefixed_name(
                        dev_spec['net'], max_length=15
                    ),
                ),
            )
            interface.append(
                lxml.etree.Element(
                    'model',
                    type='virtio',
                ),
            )
            if 'ip' in dev_spec:
                interface.append(
                    lxml.etree.Element(
                        'mac', address=utils.ipv4_to_mac(dev_spec['ip'])
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
            new_disks = lxml.etree.fromstring(dom.XMLDesc()
                                              ).xpath('devices/disk')
            for disk, xml_node in zip(self.vm._spec['disks'], new_disks):
                disk['path'] = xml_node.xpath('source')[0].attrib['file']
                disk['format'] = 'qcow2'
                snap_disk = disk.copy()
                snap_disk['path'] = xml_node.xpath('backingStore', )[0].xpath(
                    'source',
                )[0].attrib['file']
                snap_info.append(snap_disk)

            self._reclaim_disks()
            self.vm._spec['snapshots'][name] = snap_info

    def _extract_paths_gfs(self, paths, ignore_nopath):
        gfs_cli = guestfs.GuestFS(python_return_dict=True)
        try:
            disk_path = os.path.expandvars(self.vm._spec['disks'][0]['path'])
            disk_root_part = self.vm._spec['disks'][0]['metadata'].get(
                'root-partition',
                'root',
            )
            gfs_cli.add_drive_opts(disk_path, format='qcow2', readonly=1)
            gfs_cli.set_backend(os.environ.get('LIBGUESTFS_BACKEND', 'direct'))
            gfs_cli.launch()
            rootfs = [
                filesystem for filesystem in gfs_cli.list_filesystems()
                if disk_root_part in filesystem
            ]
            if not rootfs:
                raise RuntimeError(
                    'No root fs (%s) could be found for %s from list %s' % (
                        disk_root_part, disk_path,
                        str(gfs_cli.list_filesystems())
                    )
                )
            else:
                rootfs = rootfs[0]
            gfs_cli.mount_ro(rootfs, '/')
            for (guest_path, host_path) in paths:
                msg = ('Extracting guestfs://{0}:{1} to {2}').format(
                    self.vm.name(), host_path, guest_path
                )

                LOGGER.debug(msg)
                try:
                    _guestfs_copy_path(gfs_cli, guest_path, host_path)
                except ExtractPathNoPathError as err:
                    if ignore_nopath:
                        LOGGER.debug('%s: ignoring', err)
                    else:
                        raise

        finally:
            gfs_cli.shutdown()
            gfs_cli.close()

    def _reclaim_disk(self, path):
        qemu_uid = None
        try:
            qemu_uid = pwd.getpwnam('qemu').pw_uid
        except KeyError:
            pass
        if qemu_uid is not None and os.stat(path).st_uid == qemu_uid:
            utils.run_command(['sudo', '-u', 'qemu', 'chmod', 'a+rw', path])
        else:
            os.chmod(path, 0o0666)

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
                os.path.join(host_path, os.path.basename(path)),
            )
    else:
        raise ExtractPathNoPathError(
            ('unable to extract {0}: path does not '
             'exist.').format(guest_path)
        )
