#
# Copyright 2014-2017 Red Hat, Inc.
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

from future.utils import raise_from
from future.builtins import super
import functools
import json
import os
import logging
from netaddr import IPNetwork, AddrFormatError
from textwrap import dedent

from .config import config
from . import utils, log_utils

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
LOCK_NAME = 'subnet-lease.lock'


class SubnetStore(object):
    """
    SubnetStore object represents a store of subnets used by lago for network
    bridges.

    .. note:: Currently only /24 ranges are handled, and all of them under the
        192.168._min_third_octet to 192.168._max_third_octet ranges.

    The leases are stored under the store's directory (which is specified
    with the `path` argument) as json files with the form::

        [
            "/path/to/prefix/uuid/file",
            "uuid_hash",
        ]

    Where the `uuid_hash` is the 32 char uuid of the prefix (the contents of
    the uuid file at the time of doing the lease).

    The helper class :class:`Lease` is used to abstract the interaction with
    the lease files in the store (each file will be represented with a Lease
    object).

    Cleanup of stale leases is done in a lazy manner during a request for a
    lease. The store will remove at most 1 stale lease in each request (see
    SubnetStore._lease_valid for more info).

    Attributes:
        _path (str): Path to the store, if not specified defaults to the value
            of `lease_dir` in the config
        _cidr (int): Number of bits dedicated for the network address.
            Has a fixed value of 24.
        _subnet_template (str): A template for creating ip address.
            Has a fixed value of `192.168.{}.0`
        _min_third_octet (int): The minimum value of the subnets' last octet.
        _max_third_octet (int): The maximum value of the subnets' last octet.
        _min_subnet (netaddr.IPNetwork): The lowest subnet in the range of
            the store.
        _max_subnet (netaddr.IPNetwork): The highest subnet in the range of
            the store.
    """

    def __init__(
        self,
        path=None,
        min_third_octet=200,
        max_third_octet=255,
    ):

        self._path = path or config['lease_dir']
        self._cidr = 24
        self._subnet_template = '{}/{}'.format('192.168.{}.0', self._cidr)
        self._min_third_octet = min_third_octet
        self._max_third_octet = max_third_octet
        self._min_subnet = IPNetwork(
            self._subnet_template.format(min_third_octet)
        )
        self._max_subnet = IPNetwork(
            self._subnet_template.format(max_third_octet)
        )
        self._validate_lease_dir()

    def _create_lock(self):
        return utils.LockFile(
            path=os.path.join(self.path, LOCK_NAME), timeout=5
        )

    def _validate_lease_dir(self):
        """
        Validate that the directory used by this store exist,
            otherwise create it.
        """
        try:
            if not os.path.isdir(self.path):
                os.makedirs(self.path)
        except OSError as e:
            raise_from(
                LagoSubnetLeaseBadPermissionsException(self.path, e.strerror),
                e
            )

    def acquire(self, uuid_path, subnet=None):
        """
        Lease a free subnet for the given uuid path.
        If subnet is given, try to lease that subnet, otherwise try to lease a
        free subnet.

        Args:
            uuid_path (str): Path to the uuid file of a :class:`lago.Prefix`
            subnet (str): A subnet to lease.
        Returns:
            netaddr.IPAddress: An object which represents the subnet.

        Raises:
            LagoSubnetLeaseException:
                1. If this store is full
                2. If the requested subnet is already taken.
            LagoSubnetLeaseLockException:
                If the lock to self.path can't be acquired.
        """
        try:
            with self._create_lock():
                if subnet:
                    LOGGER.debug('Trying to acquire subnet {}'.format(subnet))
                    acquired_subnet = self._acquire_given_subnet(
                        uuid_path, subnet
                    )
                else:
                    LOGGER.debug('Trying to acquire a free subnet')
                    acquired_subnet = self._acquire(uuid_path)

                return acquired_subnet
        except (utils.TimerException, IOError):
            raise LagoSubnetLeaseLockException(self.path)

    def _acquire(self, uuid_path):
        """
        Lease a free network for the given uuid path

        Args:
            uuid_path (str): Path to the uuid file of a :class:`lago.Prefix`

        Returns:
            netaddr.IPNetwork: Which represents the selected subnet

        Raises:
            LagoSubnetLeaseException: If the store is full
        """
        for index in range(self._min_third_octet, self._max_third_octet + 1):
            lease = self.create_lease_object_from_idx(index)
            if self._lease_valid(lease):
                continue
            self._take_lease(lease, uuid_path, safe=False)
            return lease.to_ip_network()

        raise LagoSubnetLeaseStoreFullException(self.get_allowed_range())

    def _acquire_given_subnet(self, uuid_path, subnet):
        """
        Try to create a lease for subnet

        Args:
            uuid_path (str): Path to the uuid file of a :class:`lago.Prefix`
            subnet (str): dotted ipv4 subnet
                (for example ```192.168.200.0```)

        Returns:
            netaddr.IPNetwork: Which represents the selected subnet

        Raises:
            LagoSubnetLeaseException: If the requested subnet is not in the
                range of this store or its already been taken
        """
        lease = self.create_lease_object_from_subnet(subnet)
        self._take_lease(lease, uuid_path)

        return lease.to_ip_network()

    def _lease_valid(self, lease):
        """
        Check if the given lease exist and still has a prefix that owns it.
        If the lease exist but its prefix isn't, remove the lease from this
        store.

        Args:
            lease (lago.subnet_lease.Lease): Object representation of the
                lease

        Returns:
            str or None: If the lease and its prefix exists, return the path
                to the uuid of the prefix, else return None.
        """
        if not lease.exist:
            return None

        if lease.has_env:
            return lease.uuid_path
        else:
            self._release(lease)
            return None

    def _take_lease(self, lease, uuid_path, safe=True):
        """
        Persist the given lease to the store and make the prefix in uuid_path
        his owner

        Args:
            lease(lago.subnet_lease.Lease): Object representation of the lease
            uuid_path (str): Path to the prefix uuid
            safe (bool): If true (the default), validate the the lease
                isn't taken.

        Raises:
            LagoSubnetLeaseException: If safe == True and the lease is already
                taken.
        """
        if safe:
            lease_taken_by = self._lease_valid(lease)
            if lease_taken_by and lease_taken_by != uuid_path:
                raise LagoSubnetLeaseTakenException(
                    lease.subnet, lease_taken_by
                )

        with open(uuid_path) as f:
            uuid = f.read()
        with open(lease.path, 'wt') as f:
            utils.json_dump((uuid_path, uuid), f)

        LOGGER.debug(
            'Assigned subnet lease {} to {}'.format(lease.path, uuid_path)
        )

    def list_leases(self, uuid=None):
        """
        List current subnet leases

        Args:
            uuid(str): Filter the leases by uuid

        Returns:
            list of :class:~Lease: current leases
        """

        try:
            lease_files = os.listdir(self.path)
        except OSError as e:
            raise_from(
                LagoSubnetLeaseBadPermissionsException(self.path, e.strerror),
                e
            )

        leases = [
            self.create_lease_object_from_idx(lease_file.split('.')[0])
            for lease_file in lease_files if lease_file != LOCK_NAME
        ]
        if not uuid:
            return leases
        else:
            return [lease for lease in leases if lease.uuid == uuid]

    def release(self, subnets):
        """
        Free the lease of the given subnets

        Args:
            subnets (list of str or netaddr.IPAddress): dotted ipv4 subnet in
                CIDR notation (for example ```192.168.200.0/24```) or IPAddress
                object.

        Raises:
            LagoSubnetLeaseException: If subnet is a str and can't be parsed
            LagoSubnetLeaseLockException:
                If the lock to self.path can't be acquired.
        """

        if isinstance(subnets, str) or isinstance(subnets, IPNetwork):
            subnets = [subnets]
        subnets_iter = (
            str(subnet) if isinstance(subnet, IPNetwork) else subnet
            for subnet in subnets
        )
        try:
            with self._create_lock():
                for subnet in subnets_iter:
                    self._release(self.create_lease_object_from_subnet(subnet))
        except (utils.TimerException, IOError):
            raise LagoSubnetLeaseLockException(self.path)

    def _release(self, lease):
        """
        Free the given lease

        Args:
            lease (lago.subnet_lease.Lease): The lease to free
        """
        if lease.exist:
            os.unlink(lease.path)
            LOGGER.debug('Removed subnet lease {}'.format(lease.path))

    def _lease_owned(self, lease, current_uuid_path):
        """
        Checks if the given lease is owned by the prefix whose uuid is in
        the given path

        Note:
            The prefix must be also in the same path it was when it took the
            lease

        Args:
            path (str): Path to the lease
            current_uuid_path (str): Path to the uuid to check ownership of

        Returns:
            bool: ``True`` if the given lease in owned by the prefix,
                ``False`` otherwise
        """

        prev_uuid_path, prev_uuid = lease.metadata

        with open(current_uuid_path) as f:
            current_uuid = f.read()

        return \
            current_uuid_path == prev_uuid_path and \
            prev_uuid == current_uuid

    def create_lease_object_from_idx(self, idx):
        """
        Create a lease from self._subnet_template and put idx as its third
        octet.

        Args:
            idx (str): The value of the third octet

        Returns:
            Lease: Lease object which represents the requested subnet.

        Raises:
            LagoSubnetLeaseOutOfRangeException: If the resultant subnet is
            malformed or out of the range of the store.
        """

        return self.create_lease_object_from_subnet(
            self._subnet_template.format(idx)
        )

    def create_lease_object_from_subnet(self, subnet):
        """
        Create a lease from ip in a dotted decimal format,
        (for example `192.168.200.0/24`). the _cidr will be added if not exist
        in `subnet`.

        Args:
            subnet (str): The value of the third octet

        Returns:
            Lease: Lease object which represents the requested subnet.

        Raises:
            LagoSubnetLeaseOutOfRangeException: If the resultant subnet is
            malformed or out of the range of the store.
        """
        if '/' not in subnet:
            subnet = '{}/{}'.format(subnet, self._cidr)

        try:
            if not self.is_leasable_subnet(subnet):
                raise LagoSubnetLeaseOutOfRangeException(
                    subnet, self.get_allowed_range()
                )
        except AddrFormatError:
            raise LagoSubnetLeaseMalformedAddrException(subnet)

        return Lease(store_path=self.path, subnet=subnet)

    def is_leasable_subnet(self, subnet):
        """
        Checks if a given subnet is inside the defined provision-able range

        Args:
            subnet (str): Ip in dotted decimal format with _cidr notation
                (for example `192.168.200.0/24`)

        Returns:
            bool: True if subnet can be parsed into IPNetwork object and is
                inside the range, False otherwise

        Raises:
            netaddr.AddrFormatError: If subnet can not be parsed into an ip.
        """

        return \
            self._min_subnet <= \
            IPNetwork(subnet) <= \
            self._max_subnet

    def get_allowed_range(self):
        """
        Returns:
            str: The range of the store (with lowest and highest subnets as
                the bounds).
        """
        return '{} - {}'.format(self._min_subnet, self._max_subnet)

    @property
    def path(self):
        return self._path


class Lease(object):
    """
    Lease object is an abstraction of a lease file.

    Attributes:
        _store_path (str): Path to the lease's store.
        _subnet (str): The subnet that this lease represents
        _path (str): The path to the lease file
    """

    def __init__(self, store_path, subnet):
        self._store_path = store_path
        self._subnet = subnet
        self._path = None
        self._realise_lease_path()

    def _realise_lease_path(self):
        ip = self.subnet.split('/')[0]
        idx = ip.split('.')[2]
        self._path = os.path.join(self._store_path, '{}.lease'.format(idx))

    def to_ip_network(self):
        return IPNetwork(self.subnet)

    @property
    def valid(self):
        if self.exist:
            return self.has_env
        else:
            return False

    @property
    def metadata(self):
        with open(self.path) as f:
            uuid_path, uuid = json.load(f)

        return uuid_path, uuid

    @property
    def uuid(self):
        return self.metadata[1]

    @property
    def uuid_path(self):
        return self.metadata[0]

    @property
    def has_env(self):
        return self._has_env()

    def _has_env(self, uuid_path=None, uuid=None):
        if not (uuid_path and uuid):
            uuid_path, uuid = self.metadata

        if not os.path.isfile(uuid_path):
            return False

        with open(uuid_path, mode='rt') as f:
            if f.read() == uuid:
                return True
            else:
                return False

    @property
    def exist(self):
        return os.path.isfile(self.path)

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, data):
        self._path = data

    @property
    def subnet(self):
        return self._subnet

    @subnet.setter
    def subnet(self, data):
        self._subnet = data

    def __str__(self):
        return self.subnet


class LagoSubnetLeaseException(utils.LagoException):
    def __init__(self, msg, prv_msg=None):
        if prv_msg is not None:
            msg = msg + '\nOriginal Exception: {0}'.format(prv_msg)
        super().__init__(msg)


class LagoSubnetLeaseLockException(LagoSubnetLeaseException):
    def __init__(self, store_path):
        super().__init__(
            dedent(
                """
                Failed to acquire a lock for store {}.
                This failure can be caused by several reasons:
                1. Another 'lago' environment is using the store.
                2. A stale lock was left in the store.
                3. You don't have R/W permissions to the store.
                """.format(store_path)
            )
        )


class LagoSubnetLeaseStoreFullException(LagoSubnetLeaseException):
    def __init__(self, store_range):
        super().__init__(
            dedent(
                """
                Can't acquire subnet from range {}
                The store of subnets is full.
                You can free subnets by destroying unused lago environments'
                """.format(store_range)
            )
        )


class LagoSubnetLeaseTakenException(LagoSubnetLeaseException):
    def __init__(self, required_subnet, lease_taken_by):
        super().__init__(
            dedent(
                """
                Can't acquire subnet {}.
                The subnet is already taken by {}.
                """.format(required_subnet, lease_taken_by)
            )
        )


class LagoSubnetLeaseOutOfRangeException(LagoSubnetLeaseException):
    def __init__(self, required_subnet, store_range):
        super().__init__(
            dedent(
                """
                Subnet {} is not valid.
                Subnet should be in the range {}.
                """.format(required_subnet, store_range)
            )
        )


class LagoSubnetLeaseMalformedAddrException(LagoSubnetLeaseException):
    def __init__(self, required_subnet):
        super().__init__(
            dedent(
                """
                Address {} is not a valid ip address
                """.format(required_subnet)
            )
        )


class LagoSubnetLeaseBadPermissionsException(LagoSubnetLeaseException):
    def __init__(self, store_path, prv_msg):
        super().__init__(
            dedent(
                """
                    Failed to get access to the store at {}.
                    Please make sure that you have R/W permissions to this
                    directory and that it exists.
                    """.format(store_path)
            ),
            prv_msg=prv_msg,
        )
