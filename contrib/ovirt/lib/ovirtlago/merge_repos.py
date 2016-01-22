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

import logging
import os
import shutil
from functools import partial

import rpmUtils.arch
import rpmUtils.miscutils

import utils
from lago import log_utils

LOGGER = logging.getLogger(__name__)

LogTask = partial(log_utils.LogTask, logger=LOGGER)


def _fastcopy(source, dest):
    try:
        os.link(source, dest)
    except OSError:
        shutil.copy(source, dest)


def _get_header(path):
    ret = utils.run_command(['rpm', '-qpi', path, ], )

    if ret:
        raise RuntimeError('Failed to query RPM %s' % path)

    lines = ret.out.strip().split('\n')
    header = {}
    for line in lines:
        if line.startswith('Description'):
            break
        header[line.split(':', 1)[0].strip()] = line.split(':', 1)[1].strip()
    return header


def merge(output_dir, input_dirs):
    rpms_by_name = {}

    for input_dir in input_dirs:
        with LogTask('Processing directory %s' % input_dir):
            ret = utils.run_command(
                [
                    'find',
                    input_dir,
                    '-type',
                    'f',
                    '-name',
                    '*.rpm',
                ]
            )

            if ret:
                raise RuntimeError('Could not find the RPMs in %s' % input_dir)

            rpm_paths = ret.out.strip().split('\n')
            pkgs_by_name = {}

            for path in rpm_paths:
                hdr = _get_header(path)

                if path.endswith('.src.rpm'):
                    continue

                if hdr['Architecture'] not in rpmUtils.arch.getArchList():
                    continue

                pkgs_by_name.setdefault(hdr['Name'], [], ).append((path, hdr))

            for name, pkgs in pkgs_by_name.items():
                if name in rpms_by_name:
                    continue

                cand_path, cand_hdr = pkgs[0]

                for other_path, other_hdr in pkgs[1:]:
                    if rpmUtils.miscutils.compareEVR(
                        (
                            None,
                            cand_hdr['Version'],
                            cand_hdr['Release'],
                        ), (
                            None,
                            other_hdr['Version'],
                            other_hdr['Release'],
                        )
                    ) < 0:
                        cand_path, cand_hdr = other_path, other_hdr

                rpms_by_name[name] = cand_path

    try:
        shutil.rmtree(output_dir)
    except OSError:
        pass

    os.makedirs(output_dir)
    for path in rpms_by_name.values():
        LOGGER.debug('Copying %s to output directory', path)
        _fastcopy(path, os.path.join(output_dir, os.path.basename(path)))

    ret = utils.run_command(['createrepo', '.'], cwd=output_dir)
    if ret:
        raise RuntimeError('createrepo failed')
