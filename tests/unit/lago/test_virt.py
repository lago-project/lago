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
import functools
import mock
import pytest

import lago.virt


@pytest.fixture()
def is_alive():
    return True


@pytest.fixture()
def mocked_methods():
    return {}


@pytest.fixture()
def mock_VM(is_defined, mocked_methods, monkeypatch):
    mocks = {}
    if 'defined' not in mocked_methods:
        mocked_methods['defined'] = lambda *args: is_defined

    mock_vm_cls = mock.Mock(spec=lago.virt.VM)

    for method_name, method in mocked_methods.items():
        setattr(
            mock_vm_cls,
            method_name,
            mock.Mock(
                wraps=functools.partial(method, mock_vm_cls)
            ),
        )

    if '_env' not in mocked_methods:
        mock_vm_cls._env = mock.Mock()

    mocks['resolve_state'] = mock.Mock(return_value='shrubbery', )
    monkeypatch.setattr(
        lago.libvirt_utils.Domain,
        'resolve_state',
        mocks['resolve_state'],
    )

    return mock_vm_cls


class TestVM(object):
    @pytest.mark.parametrize(
        'is_defined,mocked_methods',
        (
            (True, {'state': lago.virt.VM.state}),
            (False, {'state': lago.virt.VM.state}),
        ),
        ids=('defined VM', 'dead VM'),
    )
    def test_state(self, mock_VM):
        if mock_VM.defined():
            assert mock_VM.state() == 'shrubbery'
        else:
            assert mock_VM.state() == 'down'
