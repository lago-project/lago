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

LIBEXEC_DIR = '/usr/libexec/lago/'
"""
LIBEXEC_DIR -
"""

CONFS_PATH = ['/etc/lago/lago.conf']
"""
CONFS_PATH - default path to first look for configuration files.
"""

CONFIG_DEFAULTS = {
    'lago':
        {
            'logdepth': 3,
            'loglevel': 'info',
            'ssh_user': 'root',
            'ssh_password': '123456',
            'ssh_tries': 100,
            'ssh_timeout': 10,
            'libvirt_url': 'qemu:///system',
            'default_vm_type': 'default',
            'default_vm_provider': 'local-libvirt',
            'lease_dir': '/var/lib/lago/subnets',
            'prefix_name': 'current',
            'reposync_dir': '/var/lib/lago',
        },
    'init':
        {
            'template_repo_path':
                'http://templates.ovirt.org/repo/repo.metadata',
            'template_store':
                '/var/lib/lago/store',
            'template_repos':
                '/var/lib/lago/repos',
        }
}
