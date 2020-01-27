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
import pytest

import lago.providers.libvirt.utils as libvirt_utils


class TestDomain(object):
    @pytest.mark.parametrize(
        'state,expected', [
            ([state_int, 9], state_desc)
            for state_int, state_desc in libvirt_utils.DOMAIN_STATES.items()
        ] + [(['imnotastate', None], 'unknown')],
        ids=list(libvirt_utils.DOMAIN_STATES.values()) + ['unknown']
    )
    def test_resolve_status(self, monkeypatch, expected, state):
        assert expected == libvirt_utils.Domain.resolve_state(state)
