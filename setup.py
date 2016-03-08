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
import os
import subprocess
from setuptools import setup


def check_output(args):
    proc = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate()

    if proc.returncode:
        raise RuntimeError(
            'Failed to run %s\nrc=%s\nstdout=\n%sstderr=%s' %
            (args, proc.returncode, stdout, stderr)
        )

    return stdout


def get_version():
    """
    Retrieves the version of the package, from the PKG-INFO file or generates
    it with the version script
    Returns:
        str: Version for the package
    Raises:
        RuntimeError: If the version could not be retrieved
    """
    if 'LAGO_VERSION' in os.environ and os.environ['LAGO_VERSION']:
        return os.environ['LAGO_VERSION']

    version = None
    if os.path.exists('PKG-INFO'):
        with open('PKG-INFO') as info_fd:
            for line in info_fd.readlines():
                if line.startswith('Version: '):
                    version = line.split(' ', 1)[-1]

    elif os.path.exists('scripts/version_manager.py'):
        version = check_output(
            ['scripts/version_manager.py', '.', 'version']
        ).strip()

    if version is None:
        raise RuntimeError('Failed to get package version')

    # py3 compatibility step
    if not isinstance(version, str) and isinstance(version, bytes):
        version = version.decode()

    return version


if __name__ == '__main__':
    os.environ['PBR_VERSION'] = get_version()
    setup(setup_requires=['pbr'], pbr=True, )
