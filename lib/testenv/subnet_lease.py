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
import functools
import json
import lockfile
import os

import constants
import utils

MIN_SUBNET = 200
MAX_SUBNET = 209

# FIXME make more robust and configurable
LEASE_DIR = constants.SUBNET_LEASE_DIR
LOCK_FILE = os.path.join(LEASE_DIR, 'leases.lock')


def is_leasable_subnet(subnet):
    pieces = map(int, subnet.split('.')[:-1])
    return (192, 168, MIN_SUBNET) <= tuple(pieces) <= (192, 168, MAX_SUBNET)


def _validate_lease_dir_present(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not os.path.isdir(LEASE_DIR):
            os.makedirs(LEASE_DIR)
        return func(*args, **kwargs)
    return wrapper


def _locked(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with lockfile.LockFile(LOCK_FILE):
            return func(*args, **kwargs)
    return wrapper


def _take_lease(path, uuid_path):
    with open(uuid_path) as f:
        uuid = f.read()
    with open(path, 'w') as f:
        utils.json_dump((uuid_path, uuid), f)


def _lease_owned(path, current_uuid_path):
    with open(path) as f:
        prev_uuid_path, prev_uuid = json.load(f)
    with open(current_uuid_path) as f:
        current_uuid = f.read()

    return current_uuid_path == prev_uuid_path and prev_uuid == current_uuid


def _lease_valid(path):
    with open(path) as f:
        uuid_path, uuid = json.load(f)

    if not os.path.isfile(uuid_path):
        return False

    with open(uuid_path) as f:
        return f.read() == uuid


@_validate_lease_dir_present
@_locked
def _acquire(uuid_path):
    for index in range(MIN_SUBNET, MAX_SUBNET + 1):
        lease_file = os.path.join(LEASE_DIR, '%d.lease' % index)
        if os.path.exists(lease_file):
            if _lease_valid(lease_file):
                continue
            else:
                os.unlink(lease_file)
        _take_lease(lease_file, uuid_path)
        return index
    return None


def acquire(uuid_path):
    return '192.168.%d.1' % _acquire(uuid_path)


@_validate_lease_dir_present
@_locked
def _release(index):
    lease_file = os.path.join(LEASE_DIR, '%d.lease' % index)
    os.unlink(lease_file)


def release(subnet):
    _release(int(subnet.split('.')[2]))
