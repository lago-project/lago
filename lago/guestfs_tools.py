#
# Copyright 2017 Red Hat, Inc.
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

import os
import guestfs
import logging
import time
import contextlib
from lago.plugins.vm import ExtractPathNoPathError
from lago.utils import LagoException

LOGGER = logging.getLogger(__name__)


class GuestFSError(LagoException):
    pass


@contextlib.contextmanager
def guestfs_conn_ro(disk):
    """
    Open a GuestFS handle and add `disk` in read only mode.

    Args:
        disk(disk path): Path to the disk.

    Yields:
        guestfs.GuestFS: Open GuestFS handle

    Raises:
        :exc:`GuestFSError`: On any guestfs operation failure
    """

    disk_path = os.path.expandvars(disk)
    conn = guestfs.GuestFS(python_return_dict=True)
    conn.add_drive_ro(disk_path)
    conn.set_backend(os.environ.get('LIBGUESTFS_BACKEND', 'direct'))
    try:
        conn.launch()
    except RuntimeError as err:
        LOGGER.debug(err)
        raise GuestFSError(
            'failed starting guestfs in readonly mode for disk: {0}'.
            format(disk)
        )
    try:
        yield conn
    finally:
        conn.shutdown()
        conn.close()


@contextlib.contextmanager
def guestfs_conn_mount_ro(disk_path, disk_root, retries=5, wait=1):
    """
    Open a GuestFS handle with `disk_path` and try mounting the root
    filesystem. `disk_root` is a hint where it should be looked and will
    only be used if GuestFS will not be able to deduce it independently.

    Note that mounting a live guest, can lead to filesystem inconsistencies,
    causing the mount operation to fail. As we use readonly mode, this is
    safe, but the operation itself can still fail. Therefore, this method
    will watch for mount failures and retry 5 times before throwing
    an exception.


    Args:
        disk_path(str): Path to the disk.
        disk_root(str): Hint what is the root device with the OS filesystem.
        retries(int): Number of retries for :func:`~guestfs.GuestFS.mount_ro`
            operation. Note that on each retry a new GuestFS handle will
            be used.
        wait(int): Time to wait between retries.

    Yields:
        guestfs.GuestFS: An open GuestFS handle.

    Raises:
        :exc:`GuestFSError`: On any guestfs operation error, including
            exceeding retries for the :func:`~guestfs.GuestFS.mount_ro`
            operation.

    """

    for attempt in range(retries):
        with guestfs_conn_ro(disk_path) as conn:
            rootfs = find_rootfs(conn, disk_root)
            try:
                conn.mount_ro(rootfs, '/')
            except RuntimeError as err:
                LOGGER.debug(err)
                if attempt < retries - 1:
                    LOGGER.debug(
                        (
                            'failed mounting %s:%s using guestfs, '
                            'attempt %s/%s'
                        ), disk_path, rootfs, attempt + 1, retries
                    )
                    time.sleep(wait)
                    continue
                else:
                    raise GuestFSError(
                        'failed mounting {0}:{1} using guestfs'.format(
                            disk_path, rootfs
                        )
                    )
            yield conn
            try:
                conn.umount(rootfs)
            except RuntimeError as err:
                LOGGER.debug(err)
                raise GuestFSError(
                    ('failed unmounting {0}:{1} using'
                     'guestfs').format(disk_path, rootfs)
                )
            break


def find_rootfs(conn, disk_root):
    """
    Find the image's device root filesystem, and return its path.

    1. Use :func:`guestfs.GuestFS.inspect_os` method. If it returns more than
        one root filesystem or None, try:
    2. Find an exact match of `disk_root` from
        :func:`guestfs.GuestFS.list_filesystems`, if none is found, try:
    3. Return the device that has the substring `disk_root` contained in it,
        from the output of :func:`guestfs.GuestFS.list_filesystems`.

    Args:
        conn(guestfs.GuestFS): Open GuestFS handle.
        disk_root(str): Root device to search for. Note that by default, if
            guestfs can deduce the filesystem, it will not be used.

    Returns:
        str: root device path

    Raises:
        :exc:`GuestFSError` if no root filesystem was found
    """
    rootfs = conn.inspect_os()
    if not rootfs or len(rootfs) > 1:
        filesystems = conn.list_filesystems()
        if disk_root in filesystems:
            rootfs = [disk_root]
        else:
            rootfs = [fs for fs in filesystems.keys() if disk_root in fs]
            if not rootfs:
                raise GuestFSError(
                    'no root fs {0} could be found from list {1}'.format(
                        disk_root, str(filesystems)
                    )
                )
    return sorted(rootfs)[0]


def extract_paths(disk_path, disk_root, paths, ignore_nopath):
    """
    Extract paths from a disk using guestfs

    Args:
        disk_path(str): path to the disk
        disk_root(str): root partition
        paths(list of tuples): files to extract in
            `[(src1, dst1), (src2, dst2)...]` format, if ``srcN`` is a
            directory in the guest, and ``dstN`` does not exist on the host,
            it will be created. If ``srcN`` is a file on the guest, it will be
            copied exactly to ``dstN``
        ignore_nopath(bool): If set to True, ignore paths in the guest that
            do not exit

    Returns:
        None

    Raises:
        :exc:`~lago.plugins.vm.ExtractPathNoPathError`: if a none existing
            path was found on the guest, and `ignore_nopath` is False.
        :exc:`~lago.plugins.vm.ExtractPathError`: on all other failures.
    """

    with guestfs_conn_mount_ro(disk_path, disk_root) as conn:
        for (guest_path, host_path) in paths:
            msg = ('Extracting guestfs://{0} to {1}').format(
                guest_path, host_path
            )

            LOGGER.debug(msg)
            try:
                _copy_path(conn, guest_path, host_path)
            except ExtractPathNoPathError as err:
                if ignore_nopath:
                    LOGGER.debug('%s - ignoring', err)
                else:
                    raise


def _copy_path(conn, guest_path, host_path):
    if conn.is_file(guest_path, followsymlinks=True):
        try:
            conn.download(guest_path, host_path)
        except RuntimeError as err:
            LOGGER.debug(err)
            raise GuestFSError(
                'failed copying file {0} to {1} using guestfs'.format(
                    guest_path, host_path
                )
            )
    elif conn.is_dir(guest_path, followsymlinks=True):
        if not os.path.isdir(host_path):
            os.makedirs(host_path)
        try:
            conn.copy_out(guest_path, host_path)
        except RuntimeError as err:
            LOGGER.debug(err)
            raise GuestFSError(
                'failed copying directory {0} to {1} using guestfs'.format(
                    guest_path, host_path
                )
            )
    else:
        raise ExtractPathNoPathError(
            ('unable to extract {0}: path does not '
             'exist.').format(guest_path)
        )
