#!/usr/bin/env python
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
"""
"""
from stevedore import ExtensionManager

#: Map of plugin type string -> setuptools entry point
PLUGIN_ENTRY_POINTS = {
    'cli': 'lago.plugins.cli',
    'out': 'lago.plugins.output',
}


class Plugin(object):
    """
    Base class for all the plugins
    """
    pass


def load_plugins(namespace):
    """
    Loads all the plugins for the given namespace

    Args:
        namespace (str): Namespace string, as in the setuptools entry_points

    Returns:
        dict of str, object: Returns the list of loaded plugins already
            instantiated
    """
    mgr = ExtensionManager(namespace=namespace, )
    return dict(
        (
            ext.name, ext.plugin if isinstance(ext.plugin, Plugin) else
            ext.plugin()
        ) for ext in mgr
    )
