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
Module that handles the leases for the subnets of the virtual network
interfaces.


.. note:: Currently only /24 ranges are handled, and all of them under the
    192.168.MIN_SUBNET to 192.168.MAX_SUBNET ranges

The leases are stored under :class:`LEASE_DIR` as json files with the form::

    [
        "/path/to/prefix/uuid/file",
        "uuid_hash",
    ]

Where the `uuid_hash` is the 32 char uuid of the prefix (the contents of the
uuid file at the time of doing the lease)

"""
import functools
import json
import lockfile
import os

import constants
import utils

#: Lower range for the allowed subnets
MIN_SUBNET = 200
#: Upper range for the allowed subnets
MAX_SUBNET = 209

# FIXME make more robust and configurable
#: Path to the directory where the net leases are stored
LEASE_DIR = constants.SUBNET_LEASE_DIR
#: Path to the net leases lock
LOCK_FILE = os.path.join(LEASE_DIR, 'leases.lock')


def is_leasable_subnet(subnet):
    """
    Checks if a given subnet is inside the defined provisionable range

    Args:
        subnet (str): Subnet or ip in dotted decimal format

    Returns:
        bool: True if subnet is inside the range, ``False`` otherwise
    """
    pieces = map(int, subnet.split('.')[:-1])
    return (192, 168, MIN_SUBNET) <= tuple(pieces) <= (192, 168, MAX_SUBNET)


def _validate_lease_dir_present(func):
    """
    Decorator that will ensure that the lease dir exists, creating it if
    necessary
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        if not os.path.isdir(LEASE_DIR):
            os.makedirs(LEASE_DIR)
        return func(*args, **kwargs)
    return wrapper


def _locked(func):
    """
    Decorator that will make sure that you have the exclusive lock for the
    leases
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with lockfile.LockFile(LOCK_FILE):
            return func(*args, **kwargs)
    return wrapper


def _take_lease(path, uuid_path):
    """
    Persist to the given leases path the prefix uuid that's in the uuid path
    passed

    Args:
        path (str): Path to the leases file
        uuid_path (str): Path to the prefix uuid

    Returns:
        None
    """
    with open(uuid_path) as f:
        uuid = f.read()
    with open(path, 'w') as f:
        utils.json_dump((uuid_path, uuid), f)


def _lease_owned(path, current_uuid_path):
    """
    Checks if the given lease is owned by the prefix whose uuid is in the given
    path

    Note:
        The prefix must be also in the same path it was when it took the lease

    Args:
        path (str): Path to the lease
        current_uuid_path (str): Path to the uuid to check ownersip of

    Returns:
        bool: ``True`` if the given lease in owned by the prefix, ``False``
            otherwise
    """
    with open(path) as f:
        prev_uuid_path, prev_uuid = json.load(f)
    with open(current_uuid_path) as f:
        current_uuid = f.read()

    return current_uuid_path == prev_uuid_path and prev_uuid == current_uuid


def _lease_valid(path):
    """
    Checs if the given lease still has a prefix that owns it

    Args:
        path (str): Path to the lease

    Returns:
        bool: ``True`` if the uuid path in the lease still exists and is the
            same as the one in the lease
    """
    with open(path) as f:
        uuid_path, uuid = json.load(f)

    if not os.path.isfile(uuid_path):
        return False

    with open(uuid_path) as f:
        return f.read() == uuid


@_validate_lease_dir_present
@_locked
def _acquire(uuid_path):
    """
    Lease a free network for the given uuid path

    Args:
        uuid_path (str): Path to the uuid file of a :class:`lago.Prefix`

    Returns:
        int or None: the third element of the dotted ip of the leased network
            or ``None`` if no lease was available

    .. todo::
        Raise exception or something instead of returning None so the
        caller can handle the failure case
    """
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
    """
    Lease a free network for the given uuid path

    Args:
        uuid_path (str): Path to the uuid file of a :class:`lago.Prefix`

    Returns:
        str: the dotted ip of the gateway for the leased net

    .. todo:: _aquire might return None, this will throw a TypeError
    """
    return '192.168.%d.1' % _acquire(uuid_path)


@_validate_lease_dir_present
@_locked
def _release(index):
    """
    Free the lease of the given subnet index

    Args:
        index (int): Third element of a dotted ip representation of the subnet,
            for example, for 1.2.3.4 it would be 3

    Returns:
        None
    """
    lease_file = os.path.join(LEASE_DIR, '%d.lease' % index)
    os.unlink(lease_file)


def release(subnet):
    """
    Free the lease of the given subnet

    Args:
        subnet (str): dotted ip or network to free the lease of

    Returns:
        None
    """
    _release(int(subnet.split('.')[2]))
