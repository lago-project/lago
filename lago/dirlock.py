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
import json
import os
import time

import lockfile

import utils


def _lock_path(path):
    return os.path.join(path, '.rwlock')


def trylock(path, excl, key_path):
    """
    Tries once to get a lock to the given dir

    Args:
        path(str): path to the directory to lock
        excl(bool): If the lock should be exclusive
        key_path(str): path to the file that contains the uid to use when
            locking

    Returns:
        bool: True if it did get a lock, False otherwise
    """
    with lockfile.LockFile(path):
        # Prune invalid users
        if os.path.exists(_lock_path(path)):
            with open(_lock_path(path)) as f:
                lock_obj = json.load(f)
        else:
            lock_obj = {'excl': False, 'users': {}}
        for other_key_path in lock_obj['users'].copy():
            if not os.path.isfile(other_key_path):
                del lock_obj['users'][other_key_path]
                continue
            with open(other_key_path) as f:
                key = f.read()
            if key != lock_obj['users'][other_key_path]:
                del lock_obj['users'][other_key_path]

        if (
            (excl and len(lock_obj['users']) != 0)
            or (not excl and lock_obj['excl'] and len(lock_obj['users']) != 0)
        ):
            success = False
        else:
            lock_obj['excl'] = excl
            with open(key_path) as f:
                lock_obj['users'][key_path] = f.read()
            success = True

        # Update lock object file
        with open(_lock_path(path), 'w') as f:
            utils.json_dump(lock_obj, f)

        return success


def lock(path, excl, key_path):
    """
    Waits until the given directory can be locked

    Args:
        path(str): Path of the directory to lock
        excl(bool): If the lock should be exclusive
        key_path(str): path to the file that contains the uid to use when
            locking

    Returns:
        None
    """
    while not trylock(path, excl, key_path):
        time.sleep(0.1)


def unlock(path, key_path):
    """
    Removes the lock of the uid in the given key file

    Args:
        path(str): Path of the directory to lock
        key_path(str): path to the file that contains the uid to remove the
            lock of

    Returns:
        None
    """
    with lockfile.LockFile(path):
        with open(_lock_path(path)) as f:
            lock_obj = json.load(f)
        del lock_obj['users'][key_path]
        with open(_lock_path(path), 'w') as f:
            utils.json_dump(lock_obj, f)
