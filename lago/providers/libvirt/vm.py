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

import functools
import logging
import os
import pwd
import time

import guestfs
import libvirt
from lxml import etree as ET

from lago import export, log_utils, sysprep, utils
from lago.config import config
from lago.plugins import vm as vm_plugin
from lago.plugins.vm import ExtractPathError, ExtractPathNoPathError
from lago.providers.libvirt import utils as libvirt_utils
from lago.providers.libvirt import cpu

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)

KDUMP_SERVICE = '/etc/systemd/system/multi-user.target.wants/kdump.service'
POSTFIX_SERVICE = '/etc/systemd/system/multi-user.target.wants/postfix.service'


class LocalLibvirtVMProvider(vm_plugin.VMProviderPlugin):
    def __init__(self, vm):
        super(LocalLibvirtVMProvider, self).__init__(vm)
        libvirt_url = config.get('libvirt_url')
        self.libvirt_con = libvirt_utils.get_libvirt_connection(
            name=self.vm.virt_env.uuid + libvirt_url,
            libvirt_url=libvirt_url,
        )
        self._libvirt_ver = self.libvirt_con.getVersion()

        caps_raw_xml = self.libvirt_con.getCapabilities()
        self._caps = ET.fromstring(caps_raw_xml)

        host_cpu = self._caps.xpath('host/cpu')[0]
        self._cpu = cpu.CPU(spec=self.vm._spec, host_cpu=host_cpu)

        # TO-DO: found a nicer way to expose these attributes to the VM
        self.vm.cpu_model = self.cpu_model
        self.vm.cpu_vendor = self.cpu_vendor

    def __del__(self):
        if self.libvirt_con is not None:
            self.libvirt_con.close()

    def start(self):
        super(LocalLibvirtVMProvider, self).start()
        if not self.defined():
            # the wait_suspend method is a work around for:
            # https://bugzilla.redhat.com/show_bug.cgi?id=1411025
            # 'LAGO__START_WAIT__SUSPEND' should be set to a float or integer
            # indicating how much time to sleep between the time the domain
            # is created in paused mode, until it is resumed.
            wait_suspend = os.environ.get('LAGO__START__WAIT_SUSPEND')
            dom_xml = self._libvirt_xml()
            LOGGER.debug('libvirt XML: %s\n', dom_xml)
            with LogTask('Starting VM %s' % self.vm.name()):
                if wait_suspend is None:
                    dom = self.libvirt_con.createXML(dom_xml)
                    if not dom:
                        raise RuntimeError(
                            'Failed to create Domain: %s' % dom_xml
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
                        dom_xml, flags=libvirt.VIR_DOMAIN_START_PAUSED
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
                self.libvirt_con.lookupByName(
                    self._libvirt_name(),
                ).destroy()

    def shutdown(self, *args, **kwargs):
        super(LocalLibvirtVMProvider, self).shutdown(*args, **kwargs)

        self._shutdown(
            libvirt_cmd=libvirt.virDomain.shutdown,
            ssh_cmd=['poweroff'],
            msg='Shutdown'
        )

        try:
            with utils.ExceptionTimer(timeout=60 * 5):
                while self.defined():
                    time.sleep(1)
        except utils.TimerException:
            raise utils.LagoUserException(
                'Failed to shutdown vm: {}'.format(self.vm.name())
            )

    def reboot(self, *args, **kwargs):
        super(LocalLibvirtVMProvider, self).reboot(*args, **kwargs)

        self._shutdown(
            libvirt_cmd=libvirt.virDomain.reboot,
            ssh_cmd=['reboot'],
            msg='Reboot'
        )

    def _shutdown(self, libvirt_cmd, ssh_cmd, msg):
        """
        Choose the invoking method (using libvirt or ssh)
        to shutdown / poweroff the domain.

        If acpi is defined in the domain use libvirt, otherwise use ssh.

        Args:
            libvirt_cmd (function): Libvirt function the invoke
            ssh_cmd (list of str): Shell command to invoke on the domain
            msg (str): Name of the command that should be inserted to the log
                message.

        Returns
            None

        Raises:
            RuntimeError: If acpi is not configured an ssh isn't available
        """
        if not self.defined():
            return

        with LogTask('{} VM {}'.format(msg, self.vm.name())):
            dom = self.libvirt_con.lookupByName(self._libvirt_name())
            dom_xml = dom.XMLDesc()

            idx = dom_xml.find('<acpi/>')
            if idx == -1:
                LOGGER.debug(
                    'acpi is not enabled on the host, '
                    '{} using ssh'.format(msg)
                )
                # TODO: change the ssh timeout exception from runtime exception
                # TODO: to custom exception and catch it.
                self.vm.ssh(ssh_cmd)
            else:
                LOGGER.debug('{} using libvirt'.format(msg))
                libvirt_cmd(dom)

    def defined(self):
        dom_names = [dom.name() for dom in self.libvirt_con.listAllDomains()]
        return self._libvirt_name() in dom_names

    def bootstrap(self):
        with LogTask('Bootstrapping %s' % self.vm.name()):
            if self.vm._spec['disks'][0]['type'] != 'empty' and self.vm._spec[
                'disks'
            ][0]['format'] != 'iso':
                root_disk = self.vm._spec['disks'][0]['path']
                mappings = {
                    'eth{0}'.format(idx): utils.ipv4_to_mac(nic['ip'])
                    for idx, nic in enumerate(self.vm.spec['nics'])
                }
                public_ssh_key = self.vm.virt_env.prefix.paths.ssh_id_rsa_pub()

                sysprep.sysprep(
                    disk=root_disk,
                    mappings=mappings,
                    distro=self.vm.distro(),
                    root_password=self.vm.root_password(),
                    public_key=public_ssh_key,
                    iscsi_name=self.vm.iscsi_name(),
                    hostname=self.vm.name(),
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
        formats_to_exclude = {'iso'}

        export_managers = [
            export.DiskExportManager.get_instance_by_type(
                dst=dst_dir,
                disk=disk,
                do_compress=compress,
                standalone=standalone,
                *args,
                **kwargs
            ) for disk in self.vm.disks
            if disk.get('format') not in formats_to_exclude
        ]

        utils.invoke_different_funcs_in_parallel(
            *map(lambda manager: manager.export, export_managers)
        )

    @vm_plugin.check_defined
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
        return utils.run_interactive_command(
            command=virsh_command,
        )

    @property
    def cpu_model(self):
        """
        VM CPU model

        Returns:
            str: CPU model

        """
        return self._cpu.model

    @property
    def cpu_vendor(self):
        """
        VM CPU Vendor

        Returns:
            str: CPU vendor
        """
        return self._cpu.vendor

    def _libvirt_name(self):
        return self.vm.virt_env.prefixed_name(self.vm.name())

    def _get_qemu_kvm_path(self):
        qemu_kvm_path = self._caps.findtext(
            "guest[os_type='hvm']/arch[@name='x86_64']/domain[@type='kvm']"
            "/emulator"
        )

        if not qemu_kvm_path:
            LOGGER.warning("hardware acceleration not available")
            qemu_kvm_path = self._caps.findtext(
                "guest[os_type='hvm']/arch[@name='x86_64']"
                "/domain[@type='qemu']/../emulator"
            )

        if not qemu_kvm_path:
            raise utils.LagoException('kvm executable not found')

        return qemu_kvm_path

    def _load_xml(self):

        args = {
            'distro': self.vm.distro(),
            'libvirt_ver': self._libvirt_ver,
            'name': self._libvirt_name(),
            'mem_size': self.vm.spec.get('memory', 16 * 1024),
            'qemu_kvm': self._get_qemu_kvm_path()
        }

        dom_raw_xml = libvirt_utils.get_domain_template(**args)

        parser = ET.XMLParser(remove_blank_text=True)
        return ET.fromstring(dom_raw_xml, parser)

    def _libvirt_xml(self):

        dom_xml = self._load_xml()

        for child in self._cpu:
            dom_xml.append(child)

        devices = dom_xml.xpath('/domain/devices')[0]

        disk = devices.xpath('disk')[0]
        devices.remove(disk)

        scsi_con_exists = False
        for disk_order, dev_spec in enumerate(self.vm._spec['disks']):

            # we have to make some adjustments
            # we use iso to indicate cdrom
            # but libvirt wants it named raw
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
                    controller = ET.Element(
                        'controller',
                        type='scsi',
                        index='0',
                        model='virtio-scsi',
                    )
                    driver = ET.Element(
                        'driver',
                        queues='{}'.format(self.vm._spec.get('vcpu', 2)),
                    )
                    controller.append(driver)
                    devices.append(controller)
                    scsi_con_exists = True

            disk = ET.Element(
                'disk',
                type='file',
                device=disk_device,
            )

            disk.append(
                ET.Element(
                    'driver',
                    name='qemu',
                    type=dev_spec['format'],
                    discard='unmap',
                ),
            )

            serial = ET.SubElement(disk, 'serial')
            serial.text = "{}".format(disk_order + 1)
            disk.append(serial)

            disk.append(
                ET.Element('boot', order="{}".format(disk_order + 1)),
            )

            disk.append(
                ET.Element(
                    'source',
                    file=os.path.expandvars(dev_spec['path']),
                ),
            )
            disk.append(
                ET.Element(
                    'target',
                    dev=dev_spec['dev'],
                    bus=bus,
                ),
            )
            devices.append(disk)

        for dev_spec in self.vm._spec['nics']:
            interface = ET.Element(
                'interface',
                type='network',
            )
            interface.append(
                ET.Element(
                    'source',
                    network=self.vm.virt_env.prefixed_name(
                        dev_spec['net'], max_length=15
                    ),
                ),
            )
            interface.append(
                ET.Element(
                    'model',
                    type='virtio',
                ),
            )
            if 'ip' in dev_spec:
                interface.append(
                    ET.Element(
                        'mac', address=utils.ipv4_to_mac(dev_spec['ip'])
                    ),
                )
            devices.append(interface)

        return ET.tostring(dom_xml, pretty_print=True)

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
            dom_xml = ET.fromstring(dom.XMLDesc())
            disks = dom_xml.xpath('devices/disk')

            snapshot_xml = ET.fromstring(
                libvirt_utils.get_template('snapshot_template.xml')
            )
            snapshot_disks = snapshot_xml.xpath('disks')[0]

            for disk in disks:
                target_dev = disk.xpath('target')[0].attrib['dev']
                snapshot_disks.append(ET.Element('disk', name=target_dev))

            try:
                dom.snapshotCreateXML(
                    ET.tostring(snapshot_xml),
                    libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_DISK_ONLY
                    | libvirt.VIR_DOMAIN_SNAPSHOT_CREATE_QUIESCE,
                )
            except libvirt.libvirtError:
                LOGGER.exception(
                    'Failed to create snapshot %s for %s',
                    name,
                    self.vm.name(),
                )
                raise

            snap_info = []
            new_disks = ET.fromstring(dom.XMLDesc()).xpath('devices/disk')
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
