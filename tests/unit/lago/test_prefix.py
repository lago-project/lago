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
from uuid import UUID
import pytest
import random
import lago
import string
from lago import prefix
from lago.utils import LagoInitException, LagoException


class PathsMock(object):
    def __init__(self, prefix):
        self.prefix = prefix

    def prefix_lagofile(self):
        return os.path.join(self.prefix, 'lagofile')


@pytest.fixture(scope='function')
def local_prefix(tmpdir, monkeypatch):
    prefix_dir = tmpdir.mkdir('.lago')
    cur_paths = PathsMock(str(prefix_dir))
    lagofile = prefix_dir.join(os.path.basename(cur_paths.prefix_lagofile()))
    lagofile.write('')
    monkeypatch.setattr(lago.paths, 'Paths', PathsMock)
    return prefix_dir


@pytest.fixture
def initalized_prefix_gen(tmpdir):
    def gen():
        counter = 0
        while True:
            inited_prefix = prefix.Prefix(
                str(tmpdir.join('workdir-{0}'.format(counter)))
            )
            inited_prefix.initialize(skip_ssh=True)
            yield inited_prefix
            counter = counter + 1

    return gen


@pytest.fixture
def random_unique_str_gen():
    def gen(length):
        used = set()
        while True:
            res = ''
            while True:
                res = ''.join(
                    [
                        random.choice(
                            string.punctuation + string.ascii_letters +
                            string.digits
                        ) for x in range(length)
                    ]
                )
                if res not in used:
                    used.add(res)
                    break
            yield res

    return gen


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
    @pytest.fixture
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
        with pytest.raises(LagoInitException, message=err_msg) as exc_info:
            empty_prefix._validate_netconfig(conf)
        exc_info.match(err_msg)


class TestInitalizedPrefix(object):
    def test_uuid_created(self, initalized_prefix_gen):
        initalized_prefix = next(initalized_prefix_gen())
        fetched_uuid = UUID(initalized_prefix.uuid, version=4)
        assert fetched_uuid.hex == initalized_prefix.uuid

    @pytest.mark.parametrize('bad_value', [-1, 10, 2, 0])
    def test_prefixed_name_raises(self, initalized_prefix_gen, bad_value):
        gen = initalized_prefix_gen()
        initalized_prefix = next(gen)
        with pytest.raises(LagoException):
            initalized_prefix.prefixed_name('a', max_length=bad_value)

    @pytest.mark.parametrize('name_length', [1, 3, 11, 150])
    @pytest.mark.parametrize('prefix_length', range(11, 16))
    def test_prefixed_name_max_length(
        self, initalized_prefix_gen, name_length, prefix_length
    ):
        gen = initalized_prefix_gen()
        initalized_prefix = next(gen)
        name = ''.join(
            [
                random.choice(
                    string.punctuation + string.ascii_letters + string.digits
                ) for x in range(name_length)
            ]
        )
        res = initalized_prefix.prefixed_name(name, max_length=prefix_length)
        assert len(res) == prefix_length
        assert res.isalnum()

    @pytest.mark.parametrize('parallel', [50])
    @pytest.mark.parametrize('name_length', [1, 2, 3, 5, 32])
    @pytest.mark.parametrize('prefix_length', range(11, 21))
    def test_prefixed_name_unique(
        self, initalized_prefix_gen, random_unique_str_gen, name_length,
        prefix_length, parallel
    ):
        gen = initalized_prefix_gen()
        prefixes = (next(gen) for _ in range(parallel))
        name = next(random_unique_str_gen(name_length))
        assert len(name) == name_length
        results = [
            p.prefixed_name(name, max_length=prefix_length) for p in prefixes
        ]
        assert len(results) == parallel
        assert all([len(res) == prefix_length for res in results])
        assert all([res.isalnum() for res in results])
        assert len(set(results)) == parallel

    @pytest.mark.parametrize(
        'num_names,name_length', [(6, 3), (20, 6), (25, 10)]
    )
    @pytest.mark.parametrize('prefix_length', range(12, 21))
    def test_prefixed_name_unique_in_prefix(
        self, initalized_prefix_gen, random_unique_str_gen, name_length,
        prefix_length, num_names
    ):

        initalized_prefix = next(initalized_prefix_gen())
        random_str = random_unique_str_gen(name_length)
        names = [next(random_str) for _ in range(num_names)]
        assert all([len(name) == name_length for name in names])
        results = [
            initalized_prefix.prefixed_name(name, max_length=prefix_length)
            for name in names
        ]

        assert len(results) == num_names
        assert all([len(res) == prefix_length for res in results])
        assert all([res.isalnum() for res in results])
        assert len(set(results)) == num_names
