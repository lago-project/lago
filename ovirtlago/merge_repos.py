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

import utils
from lago import log_utils

LOGGER = logging.getLogger(__name__)

LogTask = partial(log_utils.LogTask, logger=LOGGER)


def _fastcopy(source, dest):
    try:
        os.link(source, dest)
    except OSError:
        shutil.copyfile(source, dest)


def merge(output_dir, input_dirs):
    try:
        os.makedirs(output_dir)
    except:
        pass
    for input_dir in input_dirs:
        with LogTask('Processing directory %s' % input_dir):
            ret = utils.run_command(
                [
                    'find',
                    input_dir,
                    '-type',
                    'f',
                    '-size',
                    '+0',
                    '-name',
                    '*.rpm',
                ]
            )

            if ret.code or not ret.out:
                raise RuntimeError('Could not find the RPMs in %s' % input_dir)

            rpm_paths = ret.out.strip().split('\n')
            for path in rpm_paths:
                if "i686" not in path:
                    _fastcopy(
                        path, os.path.join(
                            output_dir, os.path.basename(path)
                        )
                    )

    try:
        ret = utils.run_command(['createrepo', output_dir], cwd=output_dir)
        if ret:
            raise RuntimeError('createrepo for %s failed', output_dir)
    except OSError:
        pass
