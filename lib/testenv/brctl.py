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
    ret, out, err = utils.run_command(_BRCTL + [command] + args)
    if ret:
        raise RuntimeError('brctl %s failed' % command)
    return ret, out, err


def _name(name):
    return 'te-%s' % name


def _set_link(name, state):
    name = _name(name)
    ret, _, _ = utils.run_command(_IP + ['link', 'set', 'dev', name, state])
    if ret:
        raise RuntimeError('Could not set %s to state %s' % (name, state))


def create(name, stp=True):
    name = _name(name)
    with utils.RollbackContext as rollback:
        _brctl('addbr', name)
        rollback.prependDefer(_brctl, 'delbr', name)
        _set_link(name, 'up')

        if stp:
            _brctl('stp', name, 'on')


def destroy(name):
    name = _name(name)
    _brctl('delbr', name)


def exists(name):
    name = _name(name)
    ret, out, err = _brctl('show', name)
    return err == ''
