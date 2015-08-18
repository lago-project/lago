#
# Copyright 2015 Red Hat, Inc.
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
import os

import utils

_DOT_SSH = '/root/.ssh'
_AUTHORIZED_KEYS = os.path.join(_DOT_SSH, 'authorized_keys')
_SELINUX_CONF_PATH = '/etc/selinux/config'


def set_hostname(hostname):
    return ('--hostname', hostname)


def set_root_password(password):
    return ('--root-password', 'password:%s' % password)


def _write_file(path, content):
    return ('--write', '%s:%s' % (path, content))


def _upload_file(local_path, remote_path):
    return ('--upload', '%s:%s' % (remote_path, local_path))


def set_iscsi_initiator_name(name):
    return _write_file(
        '/etc/iscsi/initiatorname.iscsi',
        'InitiatorName=%s' % name,
    )


def add_ssh_key(key):
    return (
        '--mkdir', _DOT_SSH,
        '--chmod', '0700:%s' % _DOT_SSH,
    ) + _upload_file(
        _AUTHORIZED_KEYS,
        key
    ) + (
        '--run-command', 'chown root.root %s' % _AUTHORIZED_KEYS,
    )


def set_selinux_mode(mode):
    return _write_file(
        _SELINUX_CONF_PATH,
        ('SELINUX=%s\n'
         'SELINUXTYPE=targeted\n') % mode,
    )


def _config_net_interface(iface, **kwargs):
    return _write_file(
        os.path.join(
            '/etc/sysconfig/network-scripts',
            'ifcfg-%s' % iface,
        ),
        '\n'.join(['%s="%s"' % (k.upper(), v) for k, v in kwargs.items()]),
    )


def config_net_interface_dhcp(iface, hwaddr):
    return _config_net_interface(
        iface,
        type='Ethernet',
        bootproto='dhcp',
        onboot='yes',
        name=iface,
        hwaddr=hwaddr,
    )


def sysprep(disk, mods):
    cmd = [
        'virt-sysprep',
        '--connect', 'qemu:///system',
        '-a', disk,
        '--selinux-relabel'
    ]
    for mod in mods:
        cmd.extend(mod)

    ret = utils.run_command(cmd)
    if ret:
        raise RuntimeError('Failed to bootstrap %s' % disk)
