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
import logging
from textwrap import dedent
from lago.validation import check_import

LOGGER = logging.getLogger(__name__)
ch = logging.StreamHandler()
ch.setLevel(logging.WARNING)
LOGGER.addHandler(ch)

if not check_import('guestfs'):
    pip_link = 'http://libguestfs.org/download/python/guestfs-1.XX.YY.tar.gz'

    msg = dedent(
        """
            WARNING: - guestfs not found. Some Lago features will not work.
            Please install it either by using your distribution package, or
            with pip.

            For Fedora/CentOS, run: yum install python2-libguestfs

            For Debian, run: apt-get install python-libguestfs

            For pip, go to http://libguestfs.org/download/python, pick
            the version and run:

            pip install {pip_link}
        """.format(pip_link=pip_link)
    )
    LOGGER.warning(msg)
