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

import os

import pytest

import lago
from lago import prefix
from lago.utils import LagoInitException


class PathsMock(object):
    def __init__(self, prefix):
        self.prefix = prefix

    def prefix_lagofile(self):
        return os.path.join(self.prefix, "lagofile")


@pytest.fixture(scope='function')
def local_prefix(tmpdir, monkeypatch):
    prefix_dir = tmpdir.mkdir('.lago')
    cur_paths = PathsMock(str(prefix_dir))
    lagofile = prefix_dir.join(os.path.basename(cur_paths.prefix_lagofile()))
    lagofile.write('')
    monkeypatch.setattr(lago.paths, 'Paths', PathsMock)
    return prefix_dir


class TestPrefixPathResolution(object):
    def test_non_existent_prefix(self):
        with pytest.raises(RuntimeError):
            prefix.Prefix.resolve_prefix_path('/')

    def test_curdir_is_prefix(self, tmpdir, monkeypatch):
        cur_paths = PathsMock(str(tmpdir))
        lagofile = tmpdir.join(os.path.basename(cur_paths.prefix_lagofile()))
        lagofile.write('')
        monkeypatch.setattr(lago.paths, 'Paths', PathsMock)
        result = prefix.Prefix.resolve_prefix_path(str(tmpdir))
        assert result == os.path.abspath(str(tmpdir))

    def test_curdir_has_prefix(self, tmpdir, local_prefix):
        result = prefix.Prefix.resolve_prefix_path(str(tmpdir))
        assert result == os.path.abspath(str(local_prefix))

    def test_parent_has_prefix(self, tmpdir, local_prefix):
        sub_dir = tmpdir.mkdir('subdir')
        result = prefix.Prefix.resolve_prefix_path(str(sub_dir))
        assert result == os.path.abspath(str(local_prefix))

    def test_many_parent_has_prefix(self, tmpdir, local_prefix):
        sub_dir = tmpdir.mkdir('subdir')
        subsub_dir = sub_dir.mkdir('subsubdir')
        result = prefix.Prefix.resolve_prefix_path(str(subsub_dir))
        assert result == os.path.abspath(str(local_prefix))


class TestPrefixNetworkInitalization(object):
    @pytest.fixture()
    def default_mgmt(self):
        return {'management': True, 'dns_domain_name': 'lago.local'}

    @pytest.mark.parametrize(
        ('conf'), [
            {
                'nets': {
                    'net-1': {}
                }
            },
            {
                'nets': {
                    'net-1': {
                        'management': True
                    }
                }
            },
            {
                'nets':
                    {
                        'net-1':
                            {
                                'management': True,
                                'dns_domain_name': 'lago.local'
                            }
                    }
            },
        ]
    )
    def test_select_mgmt_networks_single_network(
        self, empty_prefix, default_mgmt, conf
    ):
        mgmts = empty_prefix._select_mgmt_networks(conf)
        expected = {'nets': {'net-1': default_mgmt}}
        assert conf == expected
        assert mgmts == ['net-1']

    @pytest.mark.parametrize(
        ('conf'), [
            {
                'nets':
                    {
                        'net-1': {},
                        'net-2': {},
                        'mgmt_net': {
                            'management': True
                        },
                    }
            },
        ]
    )
    def test_select_mgmt_networks_one_mgmt(
        self, empty_prefix, default_mgmt, conf
    ):
        mgmts = empty_prefix._select_mgmt_networks(conf)
        expected = {
            'nets': {
                'net-1': {},
                'net-2': {},
                'mgmt_net': default_mgmt
            }
        }
        assert conf == expected
        assert mgmts == ['mgmt_net']

    @pytest.mark.parametrize(
        ('conf'), [{
            'nets': {
                'net-3': {},
                'net-2': {},
                'net-1': {}
            }
        }]
    )
    def test_select_mgmt_networks_no_mgmt_defined(
        self, empty_prefix, default_mgmt, conf
    ):
        mgmts = empty_prefix._select_mgmt_networks(conf)
        expected = {'nets': {'net-1': default_mgmt, 'net-2': {}, 'net-3': {}}}
        assert conf == expected
        assert mgmts == ['net-1']

    @pytest.mark.parametrize(
        'conf,err_msg',
        [
            (
                {
                    'domains': {
                        'vm-01': {
                            'nics': [{
                                'net': 'does_not_exist'
                            }]
                        }
                    },
                    'nets': {
                        'mgmt': {}
                    }
                }, (
                    r'Unrecognized network in vm-01: does_not_exist,\n'
                    'available: mgmt'
                )
            ),
            (
                {
                    'nets':
                        {
                            'net-1': {
                                'dns_domain_name': 'lago.local'
                            },
                            'net-2': {
                                'dns_domain_name': 'something'
                            }
                        }
                }, (
                    r'Networks: (net-1,net-2|net-2,net-1), misconfigured, '
                    'they are not marked as management, but have DNS '
                    'attributes. DNS is supported only in management networks.'
                )
            ),
            (
                {
                    'domains':
                        {
                            'vm-01': {
                                'nics': [{
                                    'net': 'none-mgmt'
                                }]
                            },
                            'vm-02':
                                {
                                    'nics':
                                        [
                                            {
                                                'net': 'mgmt'
                                            }, {
                                                'net': 'none-mgmt2'
                                            }
                                        ]
                                }
                        },
                    'nets':
                        {
                            'mgmt': {
                                'management': True
                            },
                            'none-mgmt': {},
                            'none-mgmt2': {},
                        }
                }, (
                    'VM vm-01 has no management network, please connect it to '
                    'one.'
                )
            ),
            (
                {
                    'domains':
                        {
                            'vm-01':
                                {
                                    'nics':
                                        [{
                                            'net': 'mgmt-1'
                                        }, {
                                            'net': 'mgmt-2'
                                        }]
                                },
                            'vm-02': {
                                'nics': [{
                                    'net': 'mgmt-1'
                                }]
                            }  # noqa: E123
                        },
                    'nets':
                        {
                            'mgmt-1': {
                                'management': True
                            },
                            'mgmt-2': {
                                'management': True
                            }
                        }
                },
                'VM vm-01 has more than one management network'
            )
        ]
    )
    def test_validate_netconfig(self, empty_prefix, conf, err_msg):
        with pytest.raises(LagoInitException, match=err_msg) as exc_info:
            empty_prefix._validate_netconfig(conf)
        exc_info.match(err_msg)
