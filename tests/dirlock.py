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
import tempfile
import time
import shutil
import sys
import uuid

from nose import tools

import testenv
from testenv import dirlock

prefix = None
testdir = None


def setup_prefix():
    global prefix
    prefix = testenv.Prefix(tempfile.mkdtemp())
    with open(prefix.paths.uuid(), 'w') as f:
        f.write(uuid.uuid1().hex)

    global testdir
    testdir = os.path.join(prefix.paths.prefix(), 'testdir')
    os.mkdir(testdir)


def teardown_prefix():
    shutil.rmtree(prefix.paths.prefix())


def lock_uuid(testdir, excl):
    return dirlock.lock(testdir, excl, prefix.paths.uuid())


def trylock_uuid(testdir, excl):
    return dirlock.trylock(testdir, excl, prefix.paths.uuid())


def unlock_uuid(testdir):
    return dirlock.unlock(testdir, prefix.paths.uuid())


@tools.with_setup(setup_prefix, teardown_prefix)
def test_rlock_once():
    tools.assert_true(trylock_uuid(testdir, False))


@tools.with_setup(setup_prefix, teardown_prefix)
def test_rlock_twice():
    tools.assert_true(trylock_uuid(testdir, False))
    tools.assert_true(trylock_uuid(testdir, False))


@tools.with_setup(setup_prefix, teardown_prefix)
def test_wlock_once():
    tools.assert_true(trylock_uuid(testdir, True))


@tools.with_setup(setup_prefix, teardown_prefix)
def test_wlock_twice():
    tools.assert_true(trylock_uuid(testdir, True))
    tools.assert_false(trylock_uuid(testdir, True))


@tools.with_setup(setup_prefix, teardown_prefix)
def test_wlock_twice_with_unlock():
    tools.assert_true(trylock_uuid(testdir, True))
    unlock_uuid(testdir)
    tools.assert_true(trylock_uuid(testdir, True))


@tools.with_setup(setup_prefix, teardown_prefix)
def test_prune_exipred():
    tempdir = tempfile.mkdtemp()
    try:
        def target_wlock():
            setup_prefix()
            try:
                trylock_uuid(tempdir, True)
            finally:
                teardown_prefix()

        proc = multiprocessing.Process(
            target=target_wlock
        )
        proc.start()
        proc.join()

        tools.assert_true(trylock_uuid(tempdir, True))
    finally:
        shutil.rmtree(tempdir)


@tools.with_setup(setup_prefix, teardown_prefix)
def test_lock_blocking():
    tempdir = tempfile.mkdtemp()
    try:
        cond = multiprocessing.Condition()

        def target_wlock():
            setup_prefix()
            try:
                cond.acquire()
                trylock_uuid(tempdir, True)
                cond.notify()
                cond.release()
                time.sleep(0.5)
            finally:
                teardown_prefix()
                sys.exit(0)

        proc = multiprocessing.Process(
            target=target_wlock
        )
        start = time.time()
        cond.acquire()
        proc.start()
        cond.wait()
        lock_uuid(tempdir, True)
        end = time.time()
        proc.join()

        tools.assert_true(end - start > 0.5)
    finally:
        shutil.rmtree(tempdir)
