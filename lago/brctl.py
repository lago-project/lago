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
import utils

_BRCTL = ['sudo', 'brctl']
_IP = ['sudo', 'ip']


def _brctl(command, *args):
    ret, out, err = utils.run_command(_BRCTL + [command] + list(args))
    if ret:
        raise RuntimeError(
            'brctl %s failed\nrc: %d\n\nout:\n%s\n\nerr:\n%s' %
            (command, ret, out, err)
        )
    return ret, out, err


def _set_link(name, state):
    ret, _, _ = utils.run_command(_IP + ['link', 'set', 'dev', name, state])
    if ret:
        raise RuntimeError('Could not set %s to state %s' % (name, state))


def create(name, stp=True):
    _brctl('addbr', name)
    try:
        _set_link(name, 'up')
        if stp:
            _brctl('stp', name, 'on')
    except:
        _brctl('delbr', name)
        raise


def destroy(name):
    _set_link(name, 'down')
    _brctl('delbr', name)


def exists(name):
    ret, out, _ = utils.run_command(
        ['ip', '-o', 'link', 'show', 'type', 'bridge']
    )
    if ret:
        raise RuntimeError('Failed to check if bridge {} exists'.format(name))

    for entry in out.splitlines():
        if name == entry.split(':')[1].strip():
            return True

    return False
