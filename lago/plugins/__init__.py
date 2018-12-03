#!/usr/bin/env python2
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
import logging
import warnings

LOGGER = logging.getLogger(__name__)

#: Map of plugin type string -> setuptools entry point
PLUGIN_ENTRY_POINTS = {
    'cli': 'lago.plugins.cli',
    'out': 'lago.plugins.output',
    'vm': 'lago.plugins.vm',
    'vm-service': 'lago.plugins.vm_service',
    'vm-provider': 'lago.plugins.vm_provider',
}

# Warnings that are emitted by stevedore package and we wnat to ignore.
STEVEDORE_WARN_MSG = {
    'Parameters to load are deprecated.  '
    'Call .resolve and .require separately.',
}


class PluginError(Exception):
    pass


class NoSuchPluginError(PluginError):
    pass


class Plugin(object):
    """
    Base class for all the plugins
    """
    pass


def load_plugins(namespace, instantiate=True):
    with warnings.catch_warnings(record=True) as wlist:
        plugins = _load_plugins(namespace, instantiate)
        for warn in wlist:
            msg = str(warn.message)
            if msg not in STEVEDORE_WARN_MSG:
                LOGGER.warning(msg)

    return plugins


def _load_plugins(namespace, instantiate=True):
    """
    Loads all the plugins for the given namespace

    Args:
        namespace(str): Namespace string, as in the setuptools entry_points
        instantiate(bool): If true, will instantiate the plugins too

    Returns:
        dict of str, object: Returns the list of loaded plugins
    """
    mgr = ExtensionManager(
        namespace=namespace,
        on_load_failure_callback=(
            lambda _, ep, err: LOGGER.
            warning('Could not load plugin {}: {}'.format(ep.name, err))
        )
    )
    if instantiate:
        plugins = dict(
            (
                ext.name,
                ext.plugin if isinstance(ext.plugin, Plugin) else ext.plugin()
            ) for ext in mgr
        )
    else:
        plugins = dict((ext.name, ext.plugin) for ext in mgr)

    return plugins
