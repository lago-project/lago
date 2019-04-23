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
"""
A workdir is the base directory where lago will store all the files it needs
and that are unique (not shared between workdirs).

It's basic structure is a directory with one soft link and multiple
directories, one per prefix. Where the link points to the default prefix to
use.

"""
import os
import logging
import shutil
from functools import partial, wraps
from future.builtins import super
from textwrap import dedent

from . import (prefix, utils)
from .plugins import cli
from .utils import LagoUserException

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
        perfixes(dict of str->self.prefix_class): dict with the prefixes in
        the workdir, by name
        current(str): Name of the current prefix
        prefix_class(type): Class to use when creating prefixes
    """

    def __init__(self, path, prefix_class=prefix.Prefix):
        self.path = path
        self.prefixes = {}
        self.current = None
        self.loaded = False
        self.prefix_class = prefix_class

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

        self.prefixes[prefix_name] = self.prefix_class(
            self.join(prefix_name), *args, **kwargs
        )
        self.prefixes[prefix_name].initialize()
        if self.current is None:
            self._set_current(prefix_name)

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
        found_current = False

        for dirname in dirs:
            if dirname == 'current' and os.path.islink(full_path('current')):
                self.current = os.path.basename(
                    os.readlink(full_path('current'))
                )
                found_current = True
                continue
            elif dirname == 'current':
                raise MalformedWorkdir(
                    '"%s/current" should be a soft link' % self.path
                )

            self.prefixes[dirname] = self.prefix_class(
                prefix=self.join(dirname)
            )

        if not found_current:
            raise MalformedWorkdir(
                '"%s/current" should exist and be a soft link' % self.path
            )

        self._update_current()

    def _update_current(self):
        """
        Makes sure that a current is set
        """
        if not self.current or self.current not in self.prefixes:
            if 'default' in self.prefixes:
                selected_current = 'default'
            elif self.prefixes:
                selected_current = sorted(self.prefixes.keys()).pop()
            else:
                # should never get here
                raise MalformedWorkdir(
                    'No current link and no prefixes in workdir %s' % self.path
                )

            logging.info(
                'Missing current link, setting it to %s',
                selected_current,
            )
            self._set_current(selected_current)

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

        if os.path.lexists(self.join('current')):
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
            LagoPrefixAlreadyExistsError: if prefix name already exists in the
            workdir
        """
        if os.path.exists(self.join(name)):
            raise LagoPrefixAlreadyExistsError(name, self.path)

        self.prefixes[name] = self.prefix_class(
            self.join(name), *args, **kwargs
        )
        self.prefixes[name].initialize()
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
            self.prefix_class: instance of the prefix with the given name
        """
        if name == 'current':
            name = self.current

        try:
            return self.prefixes[name]
        except KeyError:
            raise KeyError(
                'Unable to find prefix "%s" in workdir %s' % (name, self.path)
            )

    @workdir_loaded
    def destroy(self, prefix_names=None):
        """
        Destroy all the given prefixes and remove any left files if no more
        prefixes are left

        Args:
            prefix_names(list of str): list of prefix names to destroy, if None
            passed (default) will destroy all of them
        """
        if prefix_names is None:
            self.destroy(prefix_names=self.prefixes.keys())
            return

        for prefix_name in prefix_names:
            if prefix_name == 'current' and self.current in prefix_names:
                continue

            elif prefix_name == 'current':
                prefix_name = self.current

            self.get_prefix(prefix_name).destroy()
            self.prefixes.pop(prefix_name)
            if self.prefixes:
                self._update_current()

        if not self.prefixes:
            shutil.rmtree(self.path)

    @classmethod
    def resolve_workdir_path(cls, start_path=os.curdir):
        """
        Look for an existing workdir in the given path, in a path/.lago dir,
        or in a .lago dir under any of it's parent directories

        Args:
            start_path (str): path to start the search from, if None passed, it
                will use the current dir

        Returns:
            str: path to the found prefix

        Raises:
            LagoUserException: if no prefix was found
        """
        if start_path == 'auto':
            start_path = os.curdir

        cur_path = start_path

        LOGGER.debug(
            'Checking if %s is a workdir',
            os.path.abspath(cur_path),
        )
        if cls.is_workdir(cur_path):
            return os.path.abspath(cur_path)

        # now search for a .lago directory that's a workdir on any parent dir
        cur_path = os.path.join(start_path, '.lago')
        while not cls.is_workdir(cur_path):
            LOGGER.debug('%s is not a workdir', cur_path)
            cur_path = os.path.normpath(
                os.path.join(cur_path, '..', '..', '.lago')
            )
            LOGGER.debug('Checking %s for a workdir', cur_path)
            if os.path.realpath(os.path.join(cur_path, '..')) == '/':
                # no workdir found - look workdirs up the current path + 1,
                # print informative message and exit.
                candidates = []
                for path in os.listdir(os.curdir):
                    if os.path.isdir(path):
                        dirs = os.listdir(path)
                        if 'current' in dirs:
                            candidates.append(
                                os.path.abspath(os.path.join(os.curdir, path))
                            )
                        elif '.lago' in dirs:
                            candidates.append(
                                os.path.abspath(
                                    os.path.join(os.curdir, path, '.lago')
                                )
                            )
                candidates = filter(Workdir.is_possible_workdir, candidates)
                for idx in range(len(candidates)):
                    if os.path.split(candidates[idx])[1] == '.lago':
                        candidates[idx] = os.path.dirname(candidates[idx])

                msg = 'Unable to find workdir in {0}'.format(
                    os.path.abspath(start_path)
                )
                if candidates:
                    msg += '\nFound possible workdirs in: {0}'.format(
                        ', '.join(candidates)
                    )
                raise LagoUserException(msg)

        return os.path.abspath(cur_path)

    @staticmethod
    def is_possible_workdir(path):
        """
        A quick method to suggest if the path is a possible workdir.
        This does not guarantee that the workdir is not malformed, only that by
        simple heuristics it might be one.
        For a full check use :func:`is_workdir`.

        Args:
            path(str): Path

        Returns:
            bool: True if ``path`` might be a work dir.
        """
        res = False
        trails = ['initialized', 'uuid']
        try:
            res = all(
                os.path.isfile(os.path.join(path, 'current', trail))
                for trail in trails
            )
        except:
            pass
        return res

    @classmethod
    def is_workdir(cls, path):
        """
        Check if the given path is a workdir

        Args:
            path(str): Path to check

        Return:
            bool: True if the given path is a workdir
        """
        try:
            cls(path=path).load()
        except MalformedWorkdir:
            return False

        return True

    def cleanup(self):
        """
        Attempt to set a new current symlink if it is broken. If no other
        prefixes exist and the workdir is empty, try to delete the entire
        workdir.

        Raises:
            :exc:`~MalformedWorkdir`: if no prefixes were found, but the
                workdir is not empty.
        """

        current = self.join('current')
        if not os.path.exists(current):
            LOGGER.debug('found broken current symlink, removing: %s', current)
            os.unlink(self.join('current'))
            self.current = None
            try:
                self._update_current()
            except PrefixNotFound:
                if not os.listdir(self.path):
                    LOGGER.debug('workdir is empty, removing %s', self.path)
                    os.rmdir(self.path)
                else:
                    raise MalformedWorkdir(
                        (
                            'Unable to find any prefixes in {0}, '
                            'but the directory looks malformed. '
                            'Try deleting it manually.'
                        ).format(self.path)
                    )


@cli.cli_plugin(
    help=(
        'Change the current prefix link, so the default prefix that is used '
        'is a new one'
    ),
)
@cli.cli_plugin_add_argument(
    'prefix_name',
    action='store',
    help='Name of the prefix to set as current',
)
@utils.in_prefix(
    prefix_class=prefix.Prefix,
    workdir_class=Workdir,
)
def set_current(prefix_name, parent_workdir, **kwargs):
    """
    Changes the current to point to the given prefix

    Args:
        prefix_name(str): name of the prefix to set the current to
        workdir(str): path to the workdir to change the current of
    """
    parent_workdir.set_current(new_current=prefix_name)


class LagoPrefixAlreadyExistsError(utils.LagoException):
    def __init__(self, prefix_name, workdir_path):
        super().__init__(
            dedent(
                """
                Prefix with name {} already exists in workdir {}.
                Solution: specify a different prefix name or remove it.
                """.format(prefix_name, workdir_path)
            )
        )
