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
        all_files = []
        for root, _, files in os.walk(input_dir):
            all_files.extend([os.path.join(root, path) for path in files])
        logging.debug('Files in this dir: %s', repr(all_files))

        for root, _, files in os.walk(input_dir):
            rpm_files = [f for f in files
                         if f.endswith('.rpm') and not f.endswith('.src.rpm')]
            for rpm_file in rpm_files:
                ret, out, _ = utils.run_command(['rpm', '-qpi', rpm_file],
                                                cwd=root)
                if ret != 0:
                    logging.warning('Failed to get package-name of %s',
                                    rpm_file)
                    continue
                rpm_name = [l.split()[-1]
                            for l in out.split('\n')
                            if l.startswith('Name')][0]

                if rpm_name not in rpms_by_name:
                    rpms_by_name[rpm_name] = os.path.join(root, rpm_file)
                    logging.debug('Adding %s', rpm_file)
                else:
                    logging.debug('Discarding %s, preceeded by %s',
                                  rpm_file, rpms_by_name[rpm_name])

    try:
        shutil.rmtree(output_dir)
    except OSError:
        pass

    os.makedirs(output_dir)
    for path in rpms_by_name.values():
        logging.debug('Copying %s to output directory', path)
        _fastcopy(path, os.path.join(output_dir, os.path.basename(path)))

    ret, _, _ = utils.run_command(['createrepo', '.'], cwd=output_dir)
    if ret != 0:
        raise RuntimeError('createrepo failed')
