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
"""
Prefix Plugins
==============
`Prefix Provider Plugin` allows to create an alternative implementation
of high level prefix methods to define custom approach to load init file,
start, stop, or deploy the prefix.
"""
import contextlib
import functools
import logging
import os
import warnings
from abc import (ABCMeta, abstractmethod)

from .. import (config, utils, log_utils, plugins, )

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)


class PrefixPlugin(plugins.Plugin):
    __metaclass__ = ABCMeta
    """
    If you want to use a custom prefix provider (e.g. docker) you have
    to inherit from this class, and then define the
    'default_prefix_provider' in your config to be your plugin.

    It is necessary to override at least all the abstractmethods in
    order to write a prefix plugin, even if they are just running `pass`.
    """

    def __init__(self, prefix):
        self.prefix = prefix
        self.provider = self._get_prefix_provider()

    @abstractmethod
    def virt_conf_from_stream(self, *args, **kwargs):
        """
        Initialize all the virt infrastructure of the prefix

        Returns:
            None
        """
        return self.provider.virt_conf_from_stream(*args, **kwargs)

    @abstractmethod
    def start(self, *args, **kwargs):
        """
        Start a prefix

        Returns:
            None
        """
        return self.provider.start(*args, **kwargs)

    @abstractmethod
    def stop(self, *args, **kwargs):
        """
        Stop a prefix

        Returns:
            None
        """
        return self.provider.stop(*args, **kwargs)

    @abstractmethod
    def cleanup(self, *args, **kwargs):
        """
        Stop any running entities in the prefix and unitialize it

        Returns:
            None
        """
        return self.provider.cleanup(*args, **kwargs)

    @abstractmethod
    def destroy(self, *args, **kwargs):
        """
        Destroy a prefix

        Returns:
            None
        """
        return self.provider.destroy(*args, **kwargs)

    @abstractmethod
    def create_snapshots(self, *args, **kwargs):
        """
        Creates one snapshot on all the entities with the given name

        Returns:
            None
        """
        return self.provider.create_snapshots(*args, **kwargs)

    @abstractmethod
    def get_snapshots(self, *args, **kwargs):
        """
        Retrieve information on all the snapshots

        Returns:
            None
        """
        return self.provider.get_snapshots(*args, **kwargs)

    @abstractmethod
    def revert_snapshots(self, *args, **kwargs):
        """
        Revert all the snapshots with the given name

        Returns:
            None
        """
        return self.provider.revert_snapshots(*args, **kwargs)

    @abstractmethod
    def collect_artifacts(self, *args, **kwargs):
        """
        Retrieve artifacts from the given host path

        Returns:
            None
        """
        return self.provider.collect_artifacts(*args, **kwargs)

    @abstractmethod
    def deploy(self, *args, **kwargs):
        """
        Retrieve the host scripts and deploy them

        Returns:
            None
        """
        return self.provider.deploy(*args, **kwargs)

    def _get_prefix_provider(self):
        default_provider = config.get('default_prefix_provider')
        provider_name = self._spec.get('prefix-provider', default_provider)
        provider = self.prefix_providers.get(provider_name)
        self._spec['prefix-provider'] = provider_name
        return provider(prefix=self)
