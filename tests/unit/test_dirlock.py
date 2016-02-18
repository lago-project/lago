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
import multiprocessing
import os
import sys
import time
from uuid import uuid1

import pytest

from lago import dirlock
from lago.dirlock import unlock

LOCK_TYPES = {'inclusive': True, 'exclusive': False, }


# Helper functions
def get_keys(tmpdir, amount=1):
    keys = []
    for _ in range(amount):
        uuid = uuid1().hex
        key = tmpdir.join("key_" + uuid)
        key.write(uuid)
        keys.append(key)

    return keys


def get_lockdirs(tmpdir, amount=1):
    lockdirs = []
    for index in range(amount):
        lockdir = tmpdir.mkdir("lockdir_%d" % index)
        lockdirs.append(lockdir)

    return lockdirs


def trylock_exclusive(lock_dir_path, key_path):
    return dirlock.trylock(lock_dir_path, True, key_path)


# Fixtures
@pytest.fixture(scope='function')
def key_path(tmpdir):
    key = get_keys(tmpdir, amount=1)[0]
    return str(key)


@pytest.fixture(scope='function')
def lock_dir_path(tmpdir):
    lockdir = get_lockdirs(tmpdir, amount=1)[0]
    return str(lockdir)


@pytest.fixture(scope='function', params=LOCK_TYPES.keys())
def lock_type(request):
    return request.param


# Tests
def test_lock_once(lock_dir_path, key_path, lock_type):
    assert dirlock.trylock(
        path=lock_dir_path,
        excl=LOCK_TYPES[lock_type],
        key_path=key_path
    )


def test_lock_twice(lock_dir_path, key_path, lock_type):
    exclusive = LOCK_TYPES[lock_type]
    assert dirlock.trylock(
        path=lock_dir_path,
        excl=exclusive,
        key_path=key_path
    )
    if exclusive:
        assert not dirlock.trylock(
            path=lock_dir_path,
            excl=exclusive,
            key_path=key_path
        )
    else:
        assert dirlock.trylock(
            path=lock_dir_path,
            excl=exclusive,
            key_path=key_path
        )


def test_lock_twice_with_unlock(lock_dir_path, key_path, lock_type):
    exclusive = LOCK_TYPES[lock_type]
    assert dirlock.trylock(
        path=lock_dir_path,
        excl=exclusive,
        key_path=key_path
    )
    unlock(lock_dir_path, key_path)
    assert dirlock.trylock(
        path=lock_dir_path,
        excl=exclusive,
        key_path=key_path
    )


def test_prune_non_existing_users(tmpdir):
    lockdir = str(get_lockdirs(tmpdir, amount=1)[0])
    non_existing_key, good_key = [
        str(key) for key in get_keys(
            tmpdir,
            amount=2,
        )
    ]

    assert trylock_exclusive(lockdir, non_existing_key)
    os.unlink(non_existing_key)

    assert trylock_exclusive(lockdir, good_key)


def test_wait_for_unlock(tmpdir, lock_type):
    lockdir = str(get_lockdirs(tmpdir, amount=1)[0])
    blocking_key, good_key = [str(key) for key in get_keys(tmpdir, amount=2)]

    trylock_exclusive(lockdir, blocking_key)

    def blocker_agent():
        try:
            trylock_exclusive(lockdir, blocking_key)
            time.sleep(0.5)
            unlock(lockdir, blocking_key)
        finally:
            sys.exit(0)

    proc = multiprocessing.Process(target=blocker_agent)
    start = time.time()
    proc.start()
    dirlock.lock(lockdir, LOCK_TYPES[lock_type], good_key)
    end = time.time()
    proc.join()

    assert (end - start) > 0.5
