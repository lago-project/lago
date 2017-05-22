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
import os
import re
from collections import defaultdict
from io import StringIO
from warnings import warn

import configparser
from xdg import BaseDirectory as base_dirs

from lago.constants import CONFS_PATH, CONFIG_DEFAULTS
from lago.utils import argparse_to_ini


def _get_configs_path():
    """Get a list of possible configuration files, from the following
    sources:
    1. All files that exists in constants.CONFS_PATH.
    2. All XDG standard config files for "lago.conf", in reversed
    order of importance.


    Returns:
        list(str): list of files

    """

    paths = []
    xdg_paths = [
        path for path in base_dirs.load_config_paths('lago', 'lago.conf')
    ]
    paths.extend([path for path in CONFS_PATH if os.path.exists(path)])
    paths.extend(reversed(xdg_paths))
    return paths


def get_env_dict(root_section):
    """Read all Lago variables from the environment.
    The lookup format is:
    LAGO_VARNAME - will land into 'lago' section
    LAGO__SECTION1__VARNAME - will land into 'section1' section, notice
    the double '__'.
    LAGO__LONG_SECTION_NAME__VARNAME - will land into 'long_section_name'


    Returns:
        dict: dict of section configuration dicts

    Examples:
        >>> os.environ['LAGO_GLOBAL_VAR'] = 'global'
        >>> os.environ['LAGO__INIT__REPO_PATH'] = '/tmp/store'
        >>>
        >>> config.get_env_dict()
        {'init': {'repo_path': '/tmp/store'}, 'lago': {'global_var': 'global'}}

    """
    env_lago = defaultdict(dict)
    decider = re.compile(
        (
            r'^{0}(?:_(?!_)|(?P<has>__))'
            r'(?(has)(?P<section>.+?)__)'
            r'(?P<name>.+)$'
        ).format(root_section.upper())
    )

    for key, value in os.environ.iteritems():
        match = decider.match(key)
        if not match:
            continue
        if not match.group('name') or not value:
            warn(
                'empty environment variable definition:'
                '{0}, ignoring.'.format(key)
            )
        else:
            section = match.group('section') or root_section
            env_lago[section.lower()][match.group('name').lower()] = value
    return dict(env_lago)


class ConfigLoad(object):
    """Merges configuration parameters from 3 different sources:
    1. Enviornment vairables
    2. config files in .INI format
    3. argparse.ArgumentParser

    The assumed order(but not necessary) order of calls is:
    load() - load from config files and environment variables
    update_parser(parser) - update from the declared argparse parser
    update_args(args) - update from passed arguments to the parser

    """

    def __init__(self, root_section='lago', defaults={}):
        """__init__
        Args:
            root_section (str): root section in the init
            defaults (dict): Default dictonary to load, can be empty.
        """

        self.root_section = root_section
        self._defaults = defaults
        self._config = defaultdict(dict)
        self._config.update(self.load())
        self._parser = None

    def load(self):
        """
        Load all configurations from available resources, skip if empty:

            1. :attr:`default`` dict passed to :func:`ConfigLoad.__init__`.
            2. Custom paths as defined in :attr:`CONFS_PATH` in
                :class:`~lago.constants`.
            3. XDG standard paths.
            4. Environment variables.

        Returns:
            dict: dict of dicts.

        """

        configp = configparser.ConfigParser()
        configp.read_dict(self._defaults)
        for path in _get_configs_path():
            try:
                with open(path, 'r') as config_file:
                    configp.read_file(config_file)
            except IOError:
                pass
        configp.read_dict(get_env_dict(self.root_section))
        return {s: dict(configp.items(s)) for s in configp.sections()}

    def update_args(self, args):
        """Update config dictionary with parsed args, as resolved by argparse.
        Only root positional arguments that already exist will overridden.

        Args:
            args (namespace): args parsed by argparse

        """

        for arg in vars(args):
            if self.get(arg) and getattr(args, arg) is not None:
                self._config[self.root_section][arg] = getattr(args, arg)

    def update_parser(self, parser):
        """Update config dictionary with declared arguments in an argparse.parser
        New variables will be created, and existing ones overridden.

        Args:
            parser (argparse.ArgumentParser): parser to read variables from

        """

        self._parser = parser
        ini_str = argparse_to_ini(parser)
        configp = configparser.ConfigParser(allow_no_value=True)
        configp.read_dict(self._config)
        configp.read_string(ini_str)
        self._config.update(
            {s: dict(configp.items(s))
             for s in configp.sections()}
        )

    def get(self, *args):
        """Get a variable from the default section
        Args:
            *args (args): dict.get() args

        Returns:
            str: config variable

        """

        return self._config[self.root_section].get(*args)

    def __getitem__(self, key):
        """Get a variable from the default section, good for fail-fast
        if key does not exists.

        Args:
            key (str): key

        Returns:
            str: config variable

        """

        return self._config[self.root_section][key]

    def get_section(self, *args):
        """get a section dictionary
        Args:

        Returns:
            dict: section config dictionary

        """

        return self._config.get(*args)

    def get_ini(self, incl_unset=False):
        """Return the config dictionary in INI format
        Args:
            incl_unset (bool): include variables with no defaults.

        Returns:
            str: string of the config file in INI format

        """

        configp = configparser.ConfigParser(allow_no_value=True)
        configp.read_dict(self._config)
        with StringIO() as config_ini:
            if self._parser:
                self._parser.set_defaults(
                    **self.get_section(self.root_section)
                )
                argparse_ini = argparse_to_ini(
                    parser=self._parser, incl_unset=incl_unset
                )
                return argparse_ini
            else:
                configp.write(config_ini)
                return config_ini.getvalue()

    def __repr__(self):
        return self._config.__repr__()

    def __str__(self):
        return self._config.__str__()


config = ConfigLoad(defaults=CONFIG_DEFAULTS)
