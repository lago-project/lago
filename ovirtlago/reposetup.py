#!/usr/bin/env python
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

import functools
import re
import shutil
import logging
import os

from lago import log_utils
from lago.utils import (run_command, LockFile, )

from . import utils

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


class RepositoryError(Exception):
    pass


class RepositoryMergeError(RepositoryError):
    pass


def merge(output_dir, sources):
    with LogTask('Running repoman'):
        res = run_command(
            [
                'repoman',
                '--option=store.RPMStore.on_wrong_distro=copy_to_all',
                '--option=store.RPMStore.rpm_dir=', output_dir, 'add'
            ] + sources
        )
        if res.code:
            raise RepositoryMergeError(
                'Failed to merge repos %s into %s' % (sources, output_dir)
            )


def with_repo_server(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with utils.repo_server_context(args[0]):
            return func(*args, **kwargs)

    return wrapper


def _fix_reposync_issues(reposync_out, repo_path):
    """
    Fix for the issue described at::
        https://bugzilla.redhat.com/show_bug.cgi?id=1332441
    """
    LOGGER.warn(
        'Due to bug https://bugzilla.redhat.com/show_bug.cgi?id=1332441 '
        'sometimes reposync fails to update some packages that have older '
        'versions already downloaded, will remove those if any and retry'
    )
    package_regex = re.compile(r'(?P<package_name>[^:\r\s]+): \[Errno 256\]')
    for match in package_regex.findall(reposync_out):
        find_command = ['find', repo_path, '-name', match + '*', ]
        ret, out, _ = utils.run_command(find_command)

        if ret:
            raise RuntimeError('Failed to execute %s' % find_command)

        for to_remove in out.splitlines():
            if not to_remove.startswith(repo_path):
                LOGGER.warn('Skipping out-of-repo file %s', to_remove)
                continue

            LOGGER.info('Removing: %s', to_remove)
            os.unlink(to_remove)


def sync_rpm_repository(repo_path, yum_config, repos):
    lock_path = os.path.join(repo_path, 'repolock')

    if not os.path.exists(repo_path):
        os.makedirs(repo_path)

    reposync_command = [
        'reposync',
        '--config=%s' % yum_config,
        '--download_path=%s' % repo_path,
        '--newest-only',
        '--delete',
        '--cachedir=%s/cache' % repo_path,
    ] + [
        '--repoid=%s' % repo for repo in repos
    ]

    with LockFile(lock_path, timeout=180):
        with LogTask('Running reposync'):
            ret, out, _ = utils.run_command(reposync_command)
        if not ret:
            return

        _fix_reposync_issues(reposync_out=out, repo_path=repo_path)
        with LogTask('Rerunning reposync'):
            ret, _, _ = utils.run_command(reposync_command)
        if not ret:
            return

        LOGGER.warn(
            'Failed to run reposync again, that usually means that '
            'some of the local rpms might be corrupted or the metadata '
            'invalid, cleaning caches and retrying a second time'
        )
        shutil.rmtree('%s/cache' % repo_path)
        with LogTask('Rerunning reposync a last time'):
            ret, _, _ = utils.run_command(reposync_command)
        if ret:
            raise RuntimeError(
                'Failed to run reposync a second time, aborting'
            )

        return
