import functools
import os
import lxml
import logging
import pwd
import libvirt
import guestfs

from . import (
    log_utils,
    utils,
    sysprep,
    libvirt_utils,
    config,
)
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
            raise RuntimeError('VM %s is not defined' % self.name())
        return func(self, *args, **kwargs)

    return wrapper


class LocalLibvirtVM(vm.VMPlugin):
    def __init__(self, env, spec, *args, **kwargs):
        super(LocalLibvirtVM, self).__init__(env, spec, *args, **kwargs)
        libvirt_url = config.get('libvirt_url')
        self.libvirt_con = libvirt_utils.get_libvirt_connection(
            name=env.uuid + libvirt_url,
            libvirt_url=libvirt_url,
        )

    def start(self):
        super(LocalLibvirtVM, self).start()
        if not self.defined():
            with LogTask('Starting VM %s' % self.name()):
                self.libvirt_con.createXML(self._libvirt_xml())

    def stop(self):
        super(LocalLibvirtVM, self).stop()
        if self.defined():
            self._ssh_client = None
            with LogTask('Destroying VM %s' % self.name()):
                self.libvirt_con.lookupByName(
                    self._libvirt_name(),
                ).destroy()

    def defined(self):
        dom_names = [
            dom.name() for dom in self.libvirt_con.listAllDomains()
        ]
        return self._libvirt_name() in dom_names

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
                            self.virt_env.prefix.paths.ssh_id_rsa_pub(),
                            with_restorecon_fix=(self.distro() == 'fc23'),
                        ),
                        sysprep.set_iscsi_initiator_name(self.iscsi_name()),
                        sysprep.set_selinux_mode('enforcing'),
                    ] + [
                        sysprep.config_net_interface_dhcp(
                            'eth%d' % index,
                            utils.ip_to_mac(nic['ip']),
                        )
                        for index, nic in enumerate(self._spec['nics'])
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

        state = self.libvirt_con.lookupByName(
            self._libvirt_name()
        ).state()
        return libvirt_utils.Domain.resolve_state(state)

    def create_snapshot(self, name):
        if self.alive():
            self._create_live_snapshot(name)
        else:
            self._create_dead_snapshot(name)

        self.save()

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

    def has_guest_agent(self):
        try:
            self.guest_agent()
        except RuntimeError:
            return False

        return True

    def extract_paths(self, paths):
        if self.alive() and self.ssh_reachable() and self.has_guest_agent():
            self._extract_paths_live(paths=paths)
        elif not self.alive():
            self._extract_paths_dead(paths=paths)
        else:
            super(LocalLibvirtVM, self).extract_paths(paths=paths)

    @_check_defined
    def vnc_port(self):
        dom = self.libvirt_con.lookupByName(self._libvirt_name())
        dom_xml = lxml.etree.fromstring(dom.XMLDesc())
        return dom_xml.xpath('devices/graphics').pop().attrib['port']

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
        return self.virt_env.prefixed_name(self.name())

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
            '@VCPU@': self._spec.get('vcpu', 2),
            '@CPU@': self._spec.get('cpu', 2),
            '@MEM_SIZE@': self._spec.get('memory', 16 * 1024),
            '@QEMU_KVM@': qemu_kvm_path,
        }

        for key, val in replacements.items():
            dom_raw_xml = dom_raw_xml.replace(key, str(val), 1)

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
                    network=self.virt_env.prefixed_name(
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
            'Creating live snapshot named %s for %s' % (name, self.name()),
            level='debug',
        ):

            self.wait_for_ssh()
            self.guest_agent().start()
            self.ssh('sync'.split(' '))

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

    def _extract_paths_live(self, paths):
        self.guest_agent().start()
        dom = self.libvirt_con.lookupByName(self._libvirt_name())
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

    def _reclaim_disk(self, path):
        if pwd.getpwuid(os.stat(path).st_uid).pw_name == 'qemu':
            utils.run_command(['sudo', '-u', 'qemu', 'chmod', 'a+rw', path])
        else:
            os.chmod(path, 0666)

    def _reclaim_disks(self):
        for disk in self._spec['disks']:
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
