#
# Copyright 2017 Red Hat, Inc.
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

from ovirtlago import utils


class TestUtilsOvirtSDKs(object):
    @pytest.mark.parametrize(
        ('modules'),
        [(['ovirtsdk4', 'ovirtsdk']), (['ovirtsdk4', 'ovirtsdk', 'dummy'])]
    )
    def test_available_all(self, modules):
        assert utils.available_sdks(modules=modules) == ['3', '4']

    @pytest.mark.parametrize(
        ('modules', 'require'), [
            (['ovirtsdk4'], ['4']), (['ovirtsdk'], ['3']),
            (['ovirtsdk', 'dummy'], ['3'])
        ]
    )
    def test_available_one(self, modules, require):
        assert utils.available_sdks(modules=modules) == require

    @pytest.mark.parametrize(
        ('modules', 'version'), [
            (['ovirtsdk4'], '4'), (['ovirtsdk'], '3'),
            (['ovirtsdk', 'dummy'], '3'), (['ovirtsdk', 'ovirtsdk4'], '3')
        ]
    )
    def test_require_sdk(self, modules, version):
        @utils.require_sdk(version, modules)
        def foo():
            return True

        assert foo() is True

    @pytest.mark.parametrize(
        ('modules', 'version'), [
            (['ovirtsdk4'], '3'),
            (['ovirtsdk'], '4'),
            (['ovirtsdk', 'dummy'], '4'),
            ({}, '4'),
        ]
    )
    def test_require_sdk_mismatch(self, modules, version):
        with pytest.raises(RuntimeError):

            @utils.require_sdk(version=version, modules=modules)
            def foo():
                return True

            foo()
