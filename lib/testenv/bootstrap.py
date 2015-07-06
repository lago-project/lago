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
import os

import guestfs

_HOSTNAME_PATH = '/etc/hostname'
_SYSCONFIG_NETWROK_PATH = '/etc/sysconfig/network'
_SELINUX_CONF_PATH = '/etc/selinux/config'
_ISCSI_DIR = '/etc/iscsi/'
_ISCSI_INITIATOR_NAME_PATH = os.path.join(_ISCSI_DIR, 'initiatorname.iscsi')

_SSH_DIR = '/root/.ssh/'
_AUTHORIZED_KEYS = os.path.join(_SSH_DIR, 'authorized_keys')
_PERSISTENT_NET_RULES = '/etc/udev/rules.d/70-persistent-net.rules'


def _bootstrap_mod(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        def mod(gfs):
            return func(gfs, *args, **kwargs)
        return mod
    return wrapper


@_bootstrap_mod
def set_hostname(gfs, hostname):
    gfs.write(_HOSTNAME_PATH, '%s\n' % hostname)
    sysconf_net = gfs.read_file(_SYSCONFIG_NETWROK_PATH)

    sysconf_net = [
        line
        for line in sysconf_net.splitlines()
        if not line.startswith('HOSTNAME')
    ]
    sysconf_net.append('HOSTNAME=%s\n' % hostname)
    gfs.write(_SYSCONFIG_NETWROK_PATH, ''.join(sysconf_net))


@_bootstrap_mod
def set_iscsi_initiator_name(gfs, name):
    if not gfs.exists(_ISCSI_DIR):
        gfs.mkdir(_ISCSI_DIR)
    gfs.write(
        _ISCSI_INITIATOR_NAME_PATH,
        'InitiatorName=%s\n' % name,
    )


@_bootstrap_mod
def add_ssh_key(gfs, key):
    if not gfs.exists(_SSH_DIR):
        gfs.mkdir(_SSH_DIR)
        gfs.chmod(0700, _SSH_DIR)
    gfs.write(_AUTHORIZED_KEYS, key)


@_bootstrap_mod
def set_selinux(gfs, mode):
    gfs.write(
        _SELINUX_CONF_PATH,
        ('SELINUX=%s\n'
         'SELINUXTYPE=targeted\n') % mode,
    )


@_bootstrap_mod
def remove_persistent_nets(gfs):
    if gfs.exists(_PERSISTENT_NET_RULES):
        gfs.rm(_PERSISTENT_NET_RULES)


def _config_net_interface(gfs, iface, **kwargs):
    gfs.write(
        os.path.join(
            '/etc/sysconfig/network-scripts',
            'ifcfg-%s' % iface,
        ),
        '\n'.join(['%s="%s"' % (k.upper(), v) for k, v in kwargs.items()]),
    )


@_bootstrap_mod
def config_net_interface_dhcp(gfs, iface, hwaddr):
    return _config_net_interface(
        gfs,
        iface,
        type='Ethernet',
        bootproto='dhcp',
        onboot='yes',
        name=iface,
        hwaddr=hwaddr,
    )


def bootstrap(disk_path, modifications):
    g = guestfs.GuestFS(python_return_dict=True)
    g.add_drive_opts(disk_path, format='qcow2', readonly=0)
    g.set_backend('direct')
    g.launch()
    try:
        rootfs = filter(lambda x: 'root' in x, g.list_filesystems())[0]
        g.mount(rootfs, '/')

        for mod in modifications:
            mod(g)
    finally:
        g.shutdown()
        g.close()
