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
import ConfigParser
import glob
import functools
import os

_SYSTEM_CONFIG_DIR = '/etc/lago.d'
_USER_CONFIG = os.path.join(os.path.expanduser('~'), '.lago')


def _get_environ():
    return os.environ


def _get_from_env(key):
    return _get_environ()['LAGO_%s' % key.upper()]


def _get_from_files(paths, key):
    config = ConfigParser.ConfigParser()
    config.read(paths)
    try:
        return config.get('lago', key)
    except ConfigParser.Error:
        raise KeyError(key)


def _get_from_dir(path, key):
    config_files = glob.glob(os.path.join(path, '*.conf'))
    return _get_from_files(config_files, key)


def _get_providers():
    return [
        _get_from_env,
        functools.partial(
            _get_from_files,
            [_USER_CONFIG],
        ),
        functools.partial(
            _get_from_dir,
            _SYSTEM_CONFIG_DIR,
        ),
    ]


_cache = {}
_GET_DEFAULT = object()


def get(key, default=_GET_DEFAULT):
    if key in _cache:
        return _cache[key]

    for provider in _get_providers():
        try:
            val = provider(key)
            _cache[key] = val
            return val
        except KeyError:
            pass

    # Nothing was found
    if default is _GET_DEFAULT:
        raise KeyError(key)
    else:
        return default
