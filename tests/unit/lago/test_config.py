#
# Copyright 2016-2017 Red Hat, Inc.
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
import argparse
from io import StringIO
import pytest
import configparser
from mock import call, mock_open, patch

import six

from lago import config


def _ini_from_dict(configs):
    configp = configparser.ConfigParser()
    configp.read_dict(configs)
    with StringIO() as out:
        configp.write(out)
        return out.getvalue()


def _mock_open_handler(file_str):
    handler = mock_open(read_data=file_str)
    handler.return_value.__iter__ = lambda self: iter(self.readline, '')
    return handler


def _dict_to_handler(configs):
    return _mock_open_handler(_ini_from_dict(configs)).return_value


def _args_to_parser(args):
    parser = argparse.ArgumentParser(prog='test_config')
    for argname, opts in args:
        parser.add_argument(argname, **opts)
    return parser


@patch.dict(
    'lago.config.os.environ', {
        'LAGO_GLOBAL_VAR_1': 'v1',
        'LAGO__SECTION__VAR': 'v2',
        'LAGO__LONG_SECTION_NAME__LONG_VAR_NAME': 'v3',
        'IGNORE_VAR': 'ignore',
        'IGNORE__VAR__TWO': 'ignore',
    }
)
def test_get_env_dict_sections():
    assert config.get_env_dict('lago') == {
        'lago': {
            'global_var_1': 'v1'
        },
        'section': {
            'var': 'v2'
        },
        'long_section_name': {
            'long_var_name': 'v3'
        },
    }


@patch.dict(
    'lago.config.os.environ', {
        'LAGO_GLOBAL': '',
        'LAGO__NO_END': 'no-end',
        'LAGO__NO_END_': 'no-end',
        'LAGO_': 'ignore_value',
        'LAGO__': 'ignore_value',
    }
)
def test_get_env_ignores_illegal():
    assert config.get_env_dict('lago') == {}


def test_default_dict_empty():
    config_load = config.ConfigLoad(root_section='section')
    assert config_load.get_section('section') is None


@pytest.mark.parametrize(
    'defaults', [
        {
            'lago': {
                'var1': 'val1'
            },
            'init': {
                'var2': 'val2'
            },
        }, {
            'init': {
                'var1': 'var2'
            }
        }
    ]
)
def test_default_dict_loading(defaults):
    with patch('lago.config._get_configs_path', return_value=[]):
        config_load = config.ConfigLoad(defaults=defaults)
        for key, value in six.iteritems(defaults):
            assert config_load.get_section(key) == value


@patch('lago.config.open', new_callable=mock_open)
@patch('lago.config._get_configs_path', return_value=['file1'])
def test_args_loaded_from_file(mocked_configs_path, mocked_open):
    file1 = {'lago': {'arg0': 'val0'}, 'dummy': {'arg1': 'val1'}}
    mocked_open.side_effect = [_dict_to_handler(file1)]
    config_load = config.ConfigLoad()

    assert mocked_configs_path.call_count == 1
    assert mocked_open.call_args_list == [call('file1', 'r')]
    assert config_load.get_section('dummy') == {'arg1': 'val1'}
    assert config_load.get_section('lago') == {'arg0': 'val0'}


@patch('lago.config.open', new_callable=mock_open)
@patch.dict('lago.config.os.environ', {'LAGO_ENV': 'from_env'})
@patch('lago.config._get_configs_path', return_value=['file1'])
def test_env_shadows_file(mocked_configs_path, mocked_open):
    file1 = {'lago': {'env': 'from_file'}}
    mocked_open.side_effect = [_dict_to_handler(file1)]
    config_load = config.ConfigLoad()

    assert mocked_configs_path.call_count == 1
    assert mocked_open.call_args_list == [call('file1', 'r')]
    assert config_load.get_section('lago') == {'env': 'from_env'}


@patch('lago.config.open', new_callable=mock_open)
@patch('lago.config._get_configs_path', return_value=['file1', 'file2'])
def test_last_file_overrides(mocked_configs_path, mocked_open):
    file1 = {'section': {'var1': 'file1'}}
    file2 = {'section': {'var1': 'file2'}}

    mocked_open.side_effect = [
        _dict_to_handler(file1),
        _dict_to_handler(file2)
    ]
    config_load = config.ConfigLoad()

    assert mocked_configs_path.call_count == 1
    assert mocked_open.call_args_list == [
        call('file1', 'r'),
        call('file2', 'r'),
    ]
    assert config_load.get_section('section') == {'var1': 'file2'}


@patch.dict('lago.config.os.environ', {})
@patch('lago.config._get_configs_path', return_value=[])
def test_update_root_parser(mocked_configs_path):
    parser = _args_to_parser([('--arg', {'default': 'arg_default'})])
    config_load = config.ConfigLoad()
    config_load.update_parser(parser)

    assert config_load['arg'] == 'arg_default'
    assert config_load.get('arg') == 'arg_default'
    assert config_load.get_section('lago')['arg'] == 'arg_default'


@patch.dict('lago.config.os.environ', {})
@patch('lago.config.open', new_callable=mock_open)
@patch('lago.config._get_configs_path', return_value=['file1'])
def test_file_shadows_cli_default(mocked_configs_path, mocked_open):
    file1 = {'lago': {'arg': 'arg_file'}}
    mocked_open.side_effect = [
        _dict_to_handler(file1),
    ]
    parser = _args_to_parser([('--arg', {'default': 'arg_default'})])
    config_load = config.ConfigLoad()
    # although awkard looking - this mimics the round-trip in the code
    # look in cmd.py:create_parser
    parser.set_defaults(**config_load.get_section('lago'))
    config_load.update_parser(parser)

    assert mocked_configs_path.call_count == 1
    assert mocked_open.call_args_list == [call('file1', 'r')]
    assert config_load['arg'] == 'arg_file'


@patch.dict('lago.config.os.environ', {'LAGO_ARG': 'env'})
@patch('lago.config._get_configs_path', return_value=[])
def test_cli_shadows_env(mocked_configs_path):
    config_load = config.ConfigLoad()
    parser = _args_to_parser([('--arg', {'default': 'default_cli'})])
    config_load = config.ConfigLoad()
    parser.set_defaults(**config_load.get_section('lago'))
    config_load.update_parser(parser)

    assert config_load['arg'] == 'env'
    config_load.update_args(parser.parse_args(['--arg', 'cli']))
    assert config_load['arg'] == 'cli'


@patch.dict('lago.config.os.environ', {'LAGO_ARG1': 'env', 'LAGO_ARG2': 'env'})
@patch('lago.config.open', new_callable=mock_open)
@patch('lago.config._get_configs_path', return_value=['file1', 'file2'])
def test_all_sources_root_section(mocked_configs_path, mocked_open):
    file1 = {'lago': {'arg1': 'file1', 'arg2': 'file1', 'arg3': 'file1'}}
    file2 = {'lago': {'arg1': 'file2', 'arg2': 'file2'}}
    parser = _args_to_parser(
        [
            ('--arg1', {
                'default': 'parser'
            }), ('--arg2', {
                'default': 'parser'
            }), ('--arg3', {
                'default': 'parser'
            })
        ]
    )
    args = ['--arg2', 'cli']
    mocked_open.side_effect = [
        _dict_to_handler(file1),
        _dict_to_handler(file2)
    ]
    config_load = config.ConfigLoad()
    parser.set_defaults(**config_load.get_section('lago'))
    config_load.update_parser(parser)
    config_load.update_args(parser.parse_args(args))

    assert mocked_open.call_args_list == [
        call('file1', 'r'), call('file2', 'r')
    ]
    assert config_load.get_section('lago') == {
        'arg1': 'env',
        'arg2': 'cli',
        'arg3': 'file1'
    }


@patch.dict('lago.config.os.environ', {})
@patch('lago.config.open', new_callable=mock_open)
@patch('lago.config._get_configs_path', return_value=['file1'])
def test_key_only_in_file_exists(mocked_configs_path, mocked_open):
    file1 = {'custom_section': {'custom': 'custom'}}
    parser = _args_to_parser([('--arg1', {'default': 'parser'})])
    args = ['--arg1', 'cli']
    mocked_open.side_effect = [_dict_to_handler(file1)]
    config_load = config.ConfigLoad()
    parser.set_defaults(**config_load.get_section('lago', {}))
    config_load.update_parser(parser)
    config_load.update_args(parser.parse_args(args))

    assert mocked_open.call_args_list == [call('file1', 'r')]
    assert config_load.get_section('custom_section') == {'custom': 'custom'}


@pytest.mark.parametrize(
    'defaults', [
        {}, {
            'lago': {
                'var1': 'val1'
            }
        }, {
            'no_root': {
                'var1': 'val1'
            },
            'no_root2': {
                'var2': 'val2'
            }
        }
    ]
)
def test_get_ini(defaults):
    with patch('lago.config._get_configs_path', return_value=[]):
        config_load = config.ConfigLoad(defaults=defaults)
        expected = _ini_from_dict(defaults)
        assert config_load.get_ini() == expected


def test_get_ini_include_unset():
    defaults = {'lago': {'var1': 'val1'}}

    config_load = config.ConfigLoad(defaults=defaults)
    parser = _args_to_parser([('--var1', {}), ('--var2', {})])
    config_load.update_parser(parser)
    assert config_load['var1'] == 'val1'
    config_load.update_args(parser.parse_args(['--var1', 'new']))
    assert config_load['var1'] == 'new'
    ini = config_load.get_ini(incl_unset=True)

    configp = configparser.ConfigParser()
    configp.read_string(ini)
    assert configp.get('lago', 'var1') == 'new'
    assert '#var2 = None' in ini
