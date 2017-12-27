#
# Copyright 2015-2017 Red Hat, Inc.
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

import utils
import logging
import tempfile
from jinja2 import Environment, PackageLoader
import textwrap
import sys

LOGGER = logging.getLogger(__name__)

try:
    import guestfs
except ImportError:
    LOGGER.debug('guestfs not available, ignoring')


def _guestfs_version(default={'major': 1L, 'minor': 20L}):
    if 'guestfs' in sys.modules:
        g = guestfs.GuestFS(python_return_dict=True)
        guestfs_ver = g.version()
        g.close()
    else:
        guestfs_ver = default

    return guestfs_ver


def _render_template(distro, loader, **kwargs):
    env = Environment(
        loader=loader,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters['dedent'] = textwrap.dedent
    template_name = 'sysprep-{0}.j2'.format(distro)
    template = env.select_template([template_name, 'sysprep-base.j2'])
    sysprep_content = template.render(guestfs_ver=_guestfs_version(), **kwargs)
    with tempfile.NamedTemporaryFile(delete=False) as sysprep_file:
        sysprep_file.write('# {0}\n'.format(template.name))
        sysprep_file.write(sysprep_content)

    LOGGER.debug(
        ('Generated sysprep template '
         'at {0}:\n{1}').format(sysprep_file.name, sysprep_content)
    )
    return sysprep_file.name


def sysprep(disk, distro, loader=None, backend='direct', **kwargs):
    """
    Run virt-sysprep on the ``disk``, commands are built from the distro
    specific template and arguments passed in ``kwargs``. If no template is
    available it will default to ``sysprep-base.j2``.

    Args:
        disk(str): path to disk
        distro(str): distro to render template for
        loader(jinja2.BaseLoader): Jinja2 template loader, if not passed,
            will search Lago's package.
        backend(str): libguestfs backend to use
        **kwargs(dict): environment variables for Jinja2 template

    Returns:
        None

    Raises:
        RuntimeError: On virt-sysprep none 0 exit code.
    """

    if loader is None:
        loader = PackageLoader('lago', 'templates')
    sysprep_file = _render_template(distro, loader=loader, **kwargs)

    cmd = ['virt-sysprep', '-a', disk]
    cmd.extend(['--commands-from-file', sysprep_file])

    env = os.environ.copy()
    if 'LIBGUESTFS_BACKEND' not in env:
        env['LIBGUESTFS_BACKEND'] = backend

    ret = utils.run_command(cmd, env=env)
    if ret:
        raise RuntimeError(
            'Failed to bootstrap %s\ncommand:%s\nstdout:%s\nstderr:%s' % (
                disk,
                ' '.join('"%s"' % elem for elem in cmd),
                ret.out,
                ret.err,
            )
        )
