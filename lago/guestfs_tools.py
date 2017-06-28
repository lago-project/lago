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

from lago.plugins.vm import ExtractPathError, ExtractPathNoPathError

LOGGER = logging.getLogger(__name__)


def _copy_path(guestfs_conn, guest_path, host_path):
    if guestfs_conn.is_file(guest_path):
        with open(host_path, 'w') as dest_fd:
            dest_fd.write(guestfs_conn.read_file(guest_path))

    elif guestfs_conn.is_dir(guest_path):
        os.mkdir(host_path)
        for path in guestfs_conn.ls(guest_path):
            _copy_path(
                guestfs_conn,
                os.path.join(
                    guest_path,
                    path,
                ),
                os.path.join(host_path, os.path.basename(path)),
            )
    else:
        raise ExtractPathNoPathError(
            ('unable to extract {0}: path does not '
             'exist.').format(guest_path)
        )


def extract_paths(disk_path, disk_root, paths, ignore_nopath):
    """
    Extract paths from a disk using guestfs

    Args:
        disk_path(str): path to the disk
        disk_root(str): root partition
        paths(list of tuples): files to extract in
            `[(src1, dst1), (src2, dst2)...]` format.
        ignore_nopath(bool): If set to True, ignore source paths that do
        not exist

    Returns:
        None

    Raises:
        :exc:`~lago.plugins.vm.ExtractPathNoPathError`: if a none existing
            path was found on the VM, and `ignore_nopath` is False.
        :exc:`~lago.plugins.vm.ExtractPathError`: on all other failures.
    """

    gfs_cli = guestfs.GuestFS(python_return_dict=True)
    disk_path = os.path.expandvars(disk_path)
    try:
        gfs_cli.add_drive_ro(disk_path)
        gfs_cli.set_backend(os.environ.get('LIBGUESTFS_BACKEND', 'direct'))
        gfs_cli.launch()
        rootfs = [
            filesystem for filesystem in gfs_cli.list_filesystems()
            if disk_root in filesystem
        ]
        if not rootfs:
            raise ExtractPathError(
                'No root fs (%s) could be found for %s from list %s' %
                (disk_root, disk_path, str(gfs_cli.list_filesystems()))
            )
        else:
            rootfs = rootfs[0]

        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                gfs_cli.mount_ro(rootfs, '/')
                break
            except RuntimeError as err:
                if attempt <= max_attempts:
                    LOGGER.debug(err)
                    LOGGER.debug(
                        (
                            'failed mounting %s:%s using guestfs, '
                            'attempt %s/%s'
                        ), disk_path, rootfs, attempt + 1, max_attempts
                    )
                    time.sleep(1)
                else:
                    LOGGER.debug(
                        (
                            'failed mounting %s:%s using guestfs', disk_path,
                            rootfs
                        )
                    )
                    raise

        for (guest_path, host_path) in paths:
            msg = ('Extracting guestfs://{0} to {1}').format(
                guest_path, host_path
            )

            LOGGER.debug(msg)
            try:
                _copy_path(gfs_cli, guest_path, host_path)
            except ExtractPathNoPathError as err:
                if ignore_nopath:
                    LOGGER.debug('%s: ignoring', err)
                else:
                    raise

    finally:
        gfs_cli.shutdown()
        gfs_cli.close()
