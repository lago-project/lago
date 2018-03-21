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
import os


class Paths(object):
    """
    A Paths object contains methods for getting the paths to the
    directories and files which composes the prefix.

    Attributes:
        _prefix_path (str): Path to the directory of the prefix
    """

    def __init__(self, prefix_path):
        """
        Args:
            prefix_path (str): Path to the directory of the prefix
        """
        # self._prefix should be dropped in lago ver 0.44
        self.prefix = prefix_path
        self._prefix_path = prefix_path

    def prefixed(self, *args):
        return os.path.join(self._prefix_path, *args)

    def prefix_path(self):
        return self._prefix_path

    def uuid(self):
        return self.prefixed('uuid')

    def ssh_id_rsa(self):
        return self.prefixed('id_rsa')

    def ssh_id_rsa_pub(self):
        return self.prefixed('id_rsa.pub')

    def images(self, *path):
        return self.prefixed('images', *path)

    def virt(self, *path):
        return self.prefixed('virt', *path)

    def logs(self):
        return self.prefixed('logs')

    def metadata(self):
        return self.prefixed('metadata')

    def prefix_lagofile(self):
        "This file represents a prefix that's initialized"
        return self.prefixed('initialized')

    def scripts(self, *args):
        return self.prefixed('scripts', *args)
