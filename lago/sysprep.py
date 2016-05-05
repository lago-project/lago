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
_SELINUX_CONF_DIR = '/etc/selinux'
_SELINUX_CONF_PATH = os.path.join(_SELINUX_CONF_DIR, 'config')
_ISCSI_DIR = '/etc/iscsi'


def set_hostname(hostname):
    return ('--hostname', hostname)


def set_root_password(password):
    return ('--root-password', 'password:%s' % password)


def _write_file(path, content):
    return ('--write', '%s:%s' % (path, content))


def _upload_file(local_path, remote_path):
    return ('--upload', '%s:%s' % (remote_path, local_path))


def set_iscsi_initiator_name(name):
    return (
        '--mkdir',
        _ISCSI_DIR,
        '--chmod',
        '0755:%s' % _ISCSI_DIR,
    ) + _write_file(
        os.path.join(_ISCSI_DIR, 'initiatorname.iscsi'),
        'InitiatorName=%s' % name,
    )


def add_ssh_key(key, with_restorecon_fix=False):
    extra_options = (
        '--mkdir',
        _DOT_SSH,
        '--chmod',
        '0700:%s' % _DOT_SSH,
    ) + _upload_file(
        _AUTHORIZED_KEYS, key
    )
    if (not os.stat(key).st_uid == 0 or not os.stat(key).st_gid == 0):
        extra_options += (
            '--run-command',
            'chown root.root %s' % _AUTHORIZED_KEYS,
        )
    if with_restorecon_fix:
        # Fix for fc23 not relabeling on boot
        # https://bugzilla.redhat.com/1049656
        extra_options += ('--firstboot-command', 'restorecon -R /root/.ssh', )
    return extra_options


def set_selinux_mode(mode):
    return (
        '--mkdir',
        _SELINUX_CONF_DIR,
        '--chmod',
        '0755:%s' % _SELINUX_CONF_DIR,
    ) + _write_file(
        _SELINUX_CONF_PATH,
        (
            'SELINUX=%s\n'
            'SELINUXTYPE=targeted\n'
        ) % mode,
    )


def _config_net_interface(iface, **kwargs):
    return (
        '--mkdir',
        '/etc/sysconfig/network-scripts',
        '--chmod',
        '0755:/etc/sysconfig/network-scripts',
    ) + _write_file(
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


def sysprep(disk, mods, backend='direct'):
    cmd = ['virt-sysprep', '-a', disk, '--selinux-relabel']
    env = dict(os.environ.copy(), LIBGUESTFS_BACKEND=backend)
    for mod in mods:
        cmd.extend(mod)

    ret = utils.run_command(cmd, env=env)
    if ret:
        raise RuntimeError(
            'Failed to bootstrap %s\ncommand:%s\nstdout:%s\nstderr:%s' % (
                disk,
                ' '.join('"%s"' % elem for elem in cmd),
                ret.out,
                ret.err,
            )
        )
