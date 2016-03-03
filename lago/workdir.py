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
A workdir is the base directory where lago will store all the files it needs
and that are unique (not shared between workdirs).

It's basic structure is a directory with one soft link and multiple
directories, one per prefix/environment. Where the link points to the default
prefix/environment to use.

"""
import os
import logging
from functools import partial, wraps

from . import prefix
from .plugins.cli import CLIPlugin

LOGGER = logging.getLogger(__name__)


class WorkdirError(RuntimeError):
    """
    Base exception for workdir errors, catch this one to catch any workdir
    error
    """
    pass


class PrefixNotFound(WorkdirError):
    pass


class MalformedWorkdir(WorkdirError):
    pass


class PrefixAlreadyExists(WorkdirError):
    pass


def is_workdir(path):
    """
    Check if the given path is a workdir

    Args:
        path(str): Path to check

    Return:
        bool: True if the given path is a workdir
    """
    try:
        Workdir(path).load()
    except Exception:
        return False

    return True


def resolve_workdir_path(start_path=os.curdir):
    """
    Look for an existing workdir in the given path, in a path/.lago dir, or in
    a .lago dir under any of it's parent directories

    Args:
        start_path (str): path to start the search from, if None passed, it
            will use the current dir

    Returns:
        str: path to the found prefix

    Raises:
        RuntimeError: if no prefix was found
    """
    cur_path = start_path

    LOGGER.debug('Checking if %s is a workdir', os.path.abspath(cur_path), )
    if is_workdir(cur_path):
        return os.path.abspath(cur_path)

    # now search for a .lago directory that's a workdir on any parent dir
    cur_path = os.path.join(start_path, '.lago')
    while not is_workdir(cur_path):
        LOGGER.debug('%s is not a workdir', cur_path)
        cur_path = os.path.normpath(
            os.path.join(cur_path, '..', '..', '.lago')
        )
        if os.path.realpath(os.path.join(cur_path, '..')) == '/':
            raise RuntimeError(
                'Unable to find workdir for %s' % os.path.abspath(start_path)
            )

        LOGGER.debug('Checking %s for a workdir', cur_path)

    return os.path.abspath(cur_path)


def workdir_loaded(func):
    """
    Decorator to make sure that the workdir is loaded when calling the
    decorated function
    """

    @wraps(func)
    def decorator(workdir, *args, **kwargs):
        if not workdir.loaded:
            workdir.load()

        return func(workdir, *args, **kwargs)

    return decorator


class Workdir(object):
    """
    This class reperesents a base workdir, where you can store multiple
    prefixes

    Properties:
        path(str): Path to the workdir
        perfixes(dirt of str->self.PREFIX_CLASS): dict with the prefixes in
            the workdir, by name
        current(str): Name of the current prefix
    """
    PREFIX_CLASS = prefix.Prefix

    def __init__(self, path):
        self.path = path
        self.prefixes = {}
        self.current = None
        self.loaded = False

    def join(self, *args):
        """
        Gets a joined path prefixed with the workdir path

        Args:
            *args(str): path sections to join

        Returns:
            str: Joined path prefixed with the workdir path
        """
        return os.path.join(self.path, *args)

    def initialize(self, prefix_name='default', *args, **kwargs):
        """
        Initializes a workdir by adding a new prefix to the workdir.

        Args:
            prefix_name(str): Name of the new prefix to add
            *args: args to pass along to the prefix constructor
            *kwargs: kwargs to pass along to the prefix constructor

        Returns:
            The newly created prefix

        Raises:
            PrefixAlreadyExists: if the prefix name already exists in the
                workdir
        """
        if self.loaded:
            raise WorkdirError('Workdir %s already initialized' % self.path)

        if not os.path.exists(self.path):
            LOGGER.debug('Creating workdir %s', self.path)
            os.makedirs(self.path)

        self.prefixes[prefix_name] = self.PREFIX_CLASS(
            self.join(prefix_name), *args, **kwargs
        )
        self.prefixes[prefix_name].initialize()
        if self.current is None:
            self.set_current(prefix_name)

        self.load()

        return self.prefixes[prefix_name]

    def load(self):
        """
        Loads the prefixes that are available is the workdir

        Returns:
            None

        Raises:
            MalformedWorkdir: if the wordir is malformed
        """
        if self.loaded:
            LOGGER.debug('Already loaded')
            return

        try:
            basepath, dirs, _ = os.walk(self.path).next()
        except StopIteration:
            raise MalformedWorkdir('Empty dir %s' % self.path)

        full_path = partial(os.path.join, basepath)

        for dirname in dirs:
            if dirname == 'current' and os.path.islink(full_path('current')):
                self.current = os.path.basename(
                    os.readlink(full_path('current'))
                )
                continue
            elif dirname == 'current':
                raise MalformedWorkdir(
                    '"%s/current" should be a soft link' % self.path
                )

            self.prefixes[dirname] = self.PREFIX_CLASS(
                prefix=self.join(dirname)
            )

        if not self.current:
            if 'default' in self.prefixes:
                logging.info('Missing current link, setting it to default')
                self._set_current('default')
            else:
                raise MalformedWorkdir(
                    'No current link and no default prefix in workdir %s' %
                    self.path
                )

    def _set_current(self, new_current):
        """
        Change the current default prefix, for internal usage

        Args:
            new_current(str): Name of the new current prefix, it must already
                exist

        Returns:
            None

        Raises:
            PrefixNotFound: if the given prefix name does not exist in the
                workdir
        """
        new_cur_full_path = self.join(new_current)
        if not os.path.exists(new_cur_full_path):
            raise PrefixNotFound(
                'Prefix "%s" does not exist in workdir %s' %
                (new_current, self.path)
            )

        if os.path.exists(self.join('current')):
            os.unlink(self.join('current'))

        os.symlink(new_current, self.join('current'))
        self.current = new_current

    @workdir_loaded
    def set_current(self, new_current):
        """
        Change the current default prefix

        Args:
            new_current(str): Name of the new current prefix, it must already
                exist

        Returns:
            None

        Raises:
            PrefixNotFound: if the given prefix name does not exist in the
                workdir
        """
        self._set_current(new_current)

    @workdir_loaded
    def add_prefix(self, name, *args, **kwargs):
        """
        Adds a new prefix to the workdir.

        Args:
            name(str): Name of the new prefix to add
            *args: args to pass along to the prefix constructor
            *kwargs: kwargs to pass along to the prefix constructor

        Returns:
            The newly created prefix

        Raises:
            PrefixAlreadyExists: if the prefix name already exists in the
                workdir
        """
        if os.path.exists(self.join(name)):
            raise PrefixAlreadyExists(
                'Prefix with name %s already exists in workdir %s' %
                (name, self.path)
            )

        self.prefixes[name] = self.PREFIX_CLASS(
            self.join(name), *args, **kwargs
        )
        self.prefixes[name].initalize()
        if self.current is None:
            self.set_current(name)

        return self.prefixes[name]

    @workdir_loaded
    def get_prefix(self, name):
        """
        Retrieve a prefix, resolving the current one if needed

        Args:
            name(str): name of the prefix to retrieve, or current to get the
                current one

        Returns:
            self.PREFIX_CLASS: instance of the prefix with the given name
        """
        if name == 'current':
            name = self.current

        try:
            return self.prefixes[name]
        except KeyError:
            raise KeyError(
                'Unable to find prefix "%s" in workdir %s' % (name, self.path)
            )
