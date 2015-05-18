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

import rpm
import rpmUtils.arch
import rpmUtils.miscutils

import utils


def _fastcopy(source, dest):
    try:
        os.link(source, dest)
    except OSError:
        shutil.copy(source, dest)


def merge(output_dir, input_dirs):
    rpms_by_name = {}

    for input_dir in input_dirs:
        logging.info('Processing directory %s', input_dir)
        ret = utils.run_command(
            [
                'find',
                input_dir,
                '-type', 'f',
                '-name', '*.rpm',
            ]
        )

        if ret:
            raise RuntimeError('Could not find the RPMs in %s' % input_dir)

        rpm_paths = ret.out.split('\n')
        pkgs_by_name = {}

        for path in rpm_paths:
            hdr = rpmUtils.miscutils.hdrFromPackage(rpm.ts(), path)

            if hdr[rpm.RPMTAG_ARCH] not in rpmUtils.arch.getArchList():
                continue

            pkgs_by_name.setdefault(
                hdr[rpm.RPMTAG_NAME],
                [],
            ).append((path, hdr))

        for name, pkgs in pkgs_by_name.items():
            if name in rpms_by_name:
                continue

            cand_path, cand_hdr = pkgs[0]

            for other_path, other_hdr in pkgs[1:]:
                if rpmUtils.miscutils.compareEVR(
                    (
                        cand_hdr[rpm.RPMTAG_EPOCH],
                        cand_hdr[rpm.RPMTAG_VERSION],
                        cand_hdr[rpm.RPMTAG_RELEASE],
                    ),
                    (
                        other_hdr[rpm.RPMTAG_EPOCH],
                        other_hdr[rpm.RPMTAG_VERSION],
                        other_hdr[rpm.RPMTAG_RELEASE],
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
        logging.debug('Copying %s to output directory', path)
        _fastcopy(path, os.path.join(output_dir, os.path.basename(path)))

    ret = utils.run_command(['createrepo', '.'], cwd=output_dir)
    if ret:
        raise RuntimeError('createrepo failed')
