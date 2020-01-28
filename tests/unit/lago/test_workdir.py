#
# Copyright 2016 Red Hat, Inc.
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
import os
import shutil
from collections import OrderedDict

import pytest
import mock

import lago.workdir
import lago.prefix
from lago.utils import LagoUserException
from utils import generate_workdir_params


@pytest.fixture()
def workdir(tmpdir):
    return lago.workdir.Workdir(str(tmpdir))


def mock_patch(monkeypatch, topatch, attribute, **kwargs):
    mock_obj = mock.Mock(**kwargs)
    monkeypatch.setattr(topatch, attribute, mock_obj)
    return mock_obj


class TestWorkdirLoaded(object):
    def test_load_workdir(self, mock_workdir):
        decorated_func = lago.workdir.workdir_loaded(lambda wdir: wdir)
        assert not mock_workdir.loaded
        result = decorated_func(workdir=mock_workdir)
        assert mock_workdir == result
        result.load.assert_called_with()

    def test_loaded_workdir_is_not_reloaded(self, mock_workdir):
        decorated_func = lago.workdir.workdir_loaded(lambda wdir: wdir)
        mock_workdir.loaded = True
        assert mock_workdir.loaded
        result = decorated_func(workdir=mock_workdir)
        assert mock_workdir == result
        with pytest.raises(AssertionError):
            result.load.assert_called_with()


class TestWorkdir(object):
    @pytest.mark.parametrize(
        'params,expected_props',
        (
            generate_workdir_params(),
            generate_workdir_params(prefix_class=str),
        ),
        ids=('default params', 'custom prefix class'),
    )
    def test_init(self, params, expected_props):
        my_workdir = lago.workdir.Workdir(**params)
        for prop, value in expected_props.items():
            assert value == getattr(my_workdir, prop)

    @pytest.mark.parametrize(
        'paths,expected',
        (
            ([], ''), (['one'], 'one'),
            (['many', 'paths'], os.path.join('many', 'paths'))
        ),
        ids=['no paths', 'one path', 'many paths'],
    )
    def test_join(self, workdir, paths, expected):
        if expected:
            assert workdir.join(*paths) == os.path.join(workdir.path, expected)
        else:
            assert workdir.join(*paths) == os.path.join(workdir.path)

    def test_initialize_existing_workdir(self, monkeypatch):
        my_prefix = mock.Mock(spec=lago.prefix.Prefix)
        my_workdir = lago.workdir.Workdir(
            path='idontexist',
            prefix_class=my_prefix,
        )
        prefix_name = 'shrubbery name'
        mock_makedirs = mock_patch(monkeypatch, os, 'makedirs')
        mock_exists = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='exists',
            return_value=True,
        )
        mock_set_current = mock_patch(
            monkeypatch=monkeypatch,
            topatch=my_workdir,
            attribute='_set_current',
            return_value=None,
        )
        mock_load = mock_patch(
            monkeypatch=monkeypatch,
            topatch=my_workdir,
            attribute='load',
            return_value=None,
        )

        assert not my_workdir.loaded
        with pytest.raises(AssertionError):
            my_prefix.assert_called_with()
            my_prefix.initialize.assert_called_with()

        my_prefix_instance = my_workdir.initialize(prefix_name=prefix_name)

        my_prefix.assert_called_with(my_workdir.join(prefix_name))
        my_prefix_instance.initialize.assert_called_with()
        assert not mock_makedirs.method_calls
        mock_exists.assert_called_with(my_workdir.join())
        mock_set_current.assert_called_with(prefix_name)
        mock_load.assert_called_with()

    def test_initialize_non_existing_workdir(self, monkeypatch):
        my_prefix = mock.Mock(spec=lago.prefix.Prefix)
        my_workdir = lago.workdir.Workdir(
            path='idontexist',
            prefix_class=my_prefix,
        )
        prefix_name = 'shrubbery name'
        mock_makedirs = mock_patch(monkeypatch, os, 'makedirs')
        mock_exists = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='exists',
            return_value=False,
        )
        mock_set_current = mock_patch(
            monkeypatch=monkeypatch,
            topatch=my_workdir,
            attribute='_set_current',
            return_value=None,
        )
        mock_load = mock_patch(
            monkeypatch=monkeypatch,
            topatch=my_workdir,
            attribute='load',
            return_value=None,
        )

        assert not my_workdir.loaded
        with pytest.raises(AssertionError):
            my_prefix.assert_called_with()
            my_prefix.initialize.assert_called_with()

        my_prefix_instance = my_workdir.initialize(prefix_name=prefix_name)

        my_prefix.assert_called_with(my_workdir.join(prefix_name))
        my_prefix_instance.initialize.assert_called_with()
        mock_makedirs.assert_called_with(my_workdir.join())
        mock_exists.assert_called_with(my_workdir.join())
        mock_set_current.assert_called_with(prefix_name)
        mock_load.assert_called_with()

    def test_load_skip_loaded_workdir(self, mock_workdir):
        mock_workdir.loaded = True
        mock_workdir.load = lago.workdir.Workdir.load

        assert mock_workdir.load(mock_workdir) is None
        assert not mock_workdir.method_calls

    def test_load_empty_workdir_throws_exception(
        self,
        tmpdir,
        mock_workdir,
        monkeypatch,
    ):
        mock_workdir.loaded = False
        mock_workdir.load = lago.workdir.Workdir.load
        mock_walk = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os,
            attribute='walk',
            return_value=iter([(str(tmpdir), [], None)]),
        )

        with pytest.raises(lago.workdir.MalformedWorkdir):
            mock_workdir.load(mock_workdir)

        mock_walk.assert_called_with(mock_workdir.path)

    def test_load_without_current_throws_exception(
        self,
        tmpdir,
        mock_workdir,
        monkeypatch,
    ):
        mock_workdir.loaded = False
        mock_workdir.load = lago.workdir.Workdir.load
        mock_walk = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os,
            attribute='walk',
            return_value=iter([(str(tmpdir), ['notcurrent'], None)]),
        )

        with pytest.raises(lago.workdir.MalformedWorkdir):
            mock_workdir.load(mock_workdir)

        mock_walk.assert_called_with(mock_workdir.path)

    def test_load_with_current_not_symlink_throws_exception(
        self,
        tmpdir,
        mock_workdir,
        monkeypatch,
    ):
        mock_workdir.loaded = False
        mock_workdir.load = lago.workdir.Workdir.load
        mock_walk = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os,
            attribute='walk',
            return_value=iter([(str(tmpdir), ['current'], None)]),
        )
        mock_islink = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='islink',
            return_value=False,
        )

        with pytest.raises(lago.workdir.MalformedWorkdir):
            mock_workdir.load(mock_workdir)

        mock_walk.assert_called_with(mock_workdir.path)
        mock_islink.assert_called_with(os.path.join(str(tmpdir), 'current'))

    @staticmethod
    def _prepare_load_positive_run(tmpdir, mock_workdir, monkeypatch):
        mock_workdir.loaded = False
        mock_workdir.load = functools.partial(
            lago.workdir.Workdir.load,
            mock_workdir,
        )
        mock_walk = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os,
            attribute='walk',
            return_value=iter(
                [(str(tmpdir), ['current', 'another', 'extraone'], None)]
            ),
        )
        mock_islink = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='islink',
            return_value=True,
        )
        mock_readlink = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os,
            attribute='readlink',
            return_value='another',
        )

        return mock_workdir, mock_walk, mock_islink, mock_readlink

    def test_load_positive_correct_link(
        self,
        tmpdir,
        mock_workdir,
        monkeypatch,
    ):
        (
            mock_workdir,
            mock_walk,
            mock_islink,
            mock_readlink,
        ) = self._prepare_load_positive_run(
            tmpdir, mock_workdir, monkeypatch
        )  # noqa: E121

        assert mock_workdir.load() is None
        assert mock_workdir.current == 'another'
        mock_walk.assert_called_with(mock_workdir.path)
        mock_islink.assert_called_with(os.path.join(str(tmpdir), 'current'))
        mock_readlink.assert_called_with(os.path.join(str(tmpdir), 'current'))

    def test_load_positive_correct_prefixes(
        self,
        tmpdir,
        mock_workdir,
        monkeypatch,
    ):
        (mock_workdir, mock_walk, mock_islink,
         mock_readlink) = self._prepare_load_positive_run(
             tmpdir, mock_workdir, monkeypatch
         )  # noqa: E121

        assert mock_workdir.load() is None
        assert (
            set(mock_workdir.prefixes.keys()) == set(['another', 'extraone'])
        )
        mock_walk.assert_called_with(mock_workdir.path)
        mock_islink.assert_called_with(os.path.join(str(tmpdir), 'current'))
        mock_readlink.assert_called_with(os.path.join(str(tmpdir), 'current'))

    def test__update_current_skips_if_current_exists_in_prefixes(
        self,
        mock_workdir,
    ):
        mock_workdir.prefixes = {'whatever': None}
        mock_workdir.current = 'whatever'
        mock_workdir._update_current = functools.partial(
            lago.workdir.Workdir._update_current,
            mock_workdir,
        )

        assert mock_workdir._update_current() is None
        with pytest.raises(AssertionError):
            mock_workdir._set_current.assert_called_with()

    def test__update_current_on_empty_prefixes_throws_exception(
        self,
        mock_workdir,
    ):
        mock_workdir.prefixes = {}
        mock_workdir.current = None
        mock_workdir._update_current = functools.partial(
            lago.workdir.Workdir._update_current,
            mock_workdir,
        )

        with pytest.raises(lago.workdir.MalformedWorkdir):
            mock_workdir._update_current()
        with pytest.raises(AssertionError):
            mock_workdir._set_current.assert_called_with()

    def test__update_current_sets_default_if_there(
        self,
        mock_workdir,
    ):
        mock_workdir.prefixes = {'default': None, 'another': None}
        mock_workdir.current = None
        mock_workdir._update_current = functools.partial(
            lago.workdir.Workdir._update_current,
            mock_workdir,
        )

        assert mock_workdir._update_current() is None
        mock_workdir._set_current.assert_called_with('default')

    def test__update_current_sets_sorted_last_if_no_default(
        self,
        mock_workdir,
    ):
        mock_workdir.prefixes = OrderedDict()
        mock_workdir.prefixes['banother'] = None
        mock_workdir.prefixes['another'] = None
        mock_workdir.current = None
        mock_workdir._update_current = functools.partial(
            lago.workdir.Workdir._update_current,
            mock_workdir,
        )

        assert mock_workdir._update_current() is None
        mock_workdir._set_current.assert_called_with('banother')

    def test__set_current_if_prefix_does_not_exist_throw_exception(
        self,
        mock_workdir,
        monkeypatch,
    ):
        mock_exists = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='exists',
            return_value=False,
        )
        mock_workdir._set_current = functools.partial(
            lago.workdir.Workdir._set_current,
            mock_workdir,
        )
        mock_workdir.join = lambda *args: 'shrubbery'

        with pytest.raises(lago.workdir.PrefixNotFound):
            mock_workdir._set_current(new_current='idontexist')
        mock_exists.assert_called_with('shrubbery')

    def test__set_current_remove_current_link_if_already_exists(
        self,
        mock_workdir,
        monkeypatch,
    ):
        mock_exists = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='exists',
            return_value=True,
        )
        mock_lexists = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='lexists',
            return_value=True,
        )
        mock_unlink = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os,
            attribute='unlink',
            return_value=None,
        )
        mock_symlink = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os,
            attribute='symlink',
            return_value=None,
        )
        mock_workdir._set_current = functools.partial(
            lago.workdir.Workdir._set_current,
            mock_workdir,
        )
        mock_workdir.join = lambda *args: 'shrubbery'

        assert mock_workdir._set_current(new_current='idontexist') is None
        mock_exists.assert_called_with('shrubbery')
        mock_lexists.assert_called_with('shrubbery')
        mock_unlink.assert_called_with('shrubbery')
        mock_symlink.assert_called_with('idontexist', 'shrubbery')

    def test__set_current_dont_remove_current_link_if_not_there(
        self,
        mock_workdir,
        monkeypatch,
    ):
        mock_exists = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='exists',
            return_value=True,
        )
        mock_lexists = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='lexists',
            return_value=False,
        )
        mock_unlink = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os,
            attribute='unlink',
            return_value=None,
        )
        mock_symlink = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os,
            attribute='symlink',
            return_value=None,
        )
        mock_workdir._set_current = functools.partial(
            lago.workdir.Workdir._set_current,
            mock_workdir,
        )
        mock_workdir.join = lambda *args: 'shrubbery'

        assert mock_workdir._set_current(new_current='idontexist') is None
        mock_exists.assert_called_with('shrubbery')
        mock_lexists.assert_called_with('shrubbery')
        with pytest.raises(AssertionError):
            mock_unlink.assert_called_with('shrubbery')
        mock_symlink.assert_called_with('idontexist', 'shrubbery')

    def test_set_current(self, mock_workdir):
        mock_workdir.set_current = functools.partial(
            lago.workdir.Workdir.set_current,
            mock_workdir,
        )
        mock_workdir.loaded = False

        mock_workdir.set_current(new_current='idontexist')
        mock_workdir.load.assert_called_with()
        mock_workdir._set_current.assert_called_with('idontexist')

    def test_add_prefix_if_already_exists_throws_exception(
        self,
        mock_workdir,
        monkeypatch,
    ):
        mock_workdir.join = lambda *args: 'shrubbery'
        mock_workdir.add_prefix = functools.partial(
            lago.workdir.Workdir.add_prefix,
            mock_workdir,
        )
        mock_exists = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='exists',
            return_value=True,
        )

        with pytest.raises(lago.workdir.LagoPrefixAlreadyExistsError):
            mock_workdir.add_prefix(name='ni!')

        mock_exists.assert_called_with('shrubbery')

    @staticmethod
    def _add_prefix_mocks(mock_workdir, monkeypatch, prefix_name):
        mock_workdir.prefixes = {}
        mock_workdir.join = lambda *args: 'shrubbery'
        mock_workdir.add_prefix = functools.partial(
            lago.workdir.Workdir.add_prefix,
            mock_workdir,
        )
        mock_workdir.prefix_class = mock.Mock(spec=lago.prefix.Prefix)
        mock_exists = mock_patch(
            monkeypatch=monkeypatch,
            topatch=os.path,
            attribute='exists',
            return_value=False,
        )

        result = mock_workdir.add_prefix(name=prefix_name)

        result.initialize.assert_called_with()
        mock_exists.assert_called_with('shrubbery')
        assert prefix_name in mock_workdir.prefixes
        assert mock_workdir.prefixes[prefix_name] == result
        return mock_workdir, mock_exists

    def test_add_prefix_set_current_if_its_none(
        self,
        mock_workdir,
        monkeypatch,
    ):
        prefix_name = 'ni!'
        mock_workdir.current = None
        mock_workdir, mock_exists = self._add_prefix_mocks(
            mock_workdir,
            monkeypatch,
            prefix_name,
        )

        mock_workdir.set_current.assert_called_with(prefix_name)

    def test_add_prefix_dont_set_current_if_its_not_none(
        self,
        mock_workdir,
        monkeypatch,
    ):
        prefix_name = 'ni!'
        mock_workdir.current = 'another'
        mock_workdir, mock_exists = self._add_prefix_mocks(
            mock_workdir,
            monkeypatch,
            prefix_name,
        )

        with pytest.raises(AssertionError):
            mock_workdir.set_current.assert_called_with(prefix_name)

    def test_get_prefix_when_not_found_throws_exception(self, mock_workdir):
        mock_workdir.prefixes = {}
        mock_workdir.get_prefix = functools.partial(
            lago.workdir.Workdir.get_prefix,
            mock_workdir,
        )

        with pytest.raises(KeyError):
            mock_workdir.get_prefix('idontexist')

    def test_get_prefix_retrieves_current(self, mock_workdir):
        mock_workdir.current = 'another'
        mock_workdir.prefixes = {'another': 'awonder'}
        mock_workdir.get_prefix = functools.partial(
            lago.workdir.Workdir.get_prefix,
            mock_workdir,
        )

        assert mock_workdir.get_prefix('current') == 'awonder'

    def test_get_prefix_retrieves_explicit_prefix(self, mock_workdir):
        mock_workdir.current = 'another_one'
        mock_workdir.prefixes = {'another': 'awonder'}
        mock_workdir.get_prefix = functools.partial(
            lago.workdir.Workdir.get_prefix,
            mock_workdir,
        )

        assert mock_workdir.get_prefix('another') == 'awonder'

    def _destroy_mocks(self, monkeypatch, mock_workdir):
        mock_rmtree = mock_patch(
            monkeypatch=monkeypatch,
            topatch=shutil,
            attribute='rmtree',
            return_value=False,
        )
        mock_workdir.path = 'shrubbery'
        mock_workdir.current = 'nini!'
        mock_workdir.prefixes = {
            'ni!': mock.Mock(spec=lago.prefix.Prefix),
            'nini!': mock.Mock(spec=lago.prefix.Prefix),
            'ninini!': mock.Mock(spec=lago.prefix.Prefix),
        }
        mock_workdir.destroy = functools.partial(
            lago.workdir.Workdir.destroy,
            mock_workdir,
        )

        return mock_rmtree, mock_workdir

    @pytest.mark.parametrize(
        'to_destroy',
        (
            None,
            [],
            ['ni!'],
            ['nini!', 'ninini!'],
            ['ni!', 'nini!', 'ninini!'],
        ),
        ids=(
            'None as prefixes',
            'empty list as prefixes',
            'one prefix',
            'many prefixes',
            'all prefixes',
        ),
    )
    def test_destroy(
        self,
        mock_workdir,
        monkeypatch,
        to_destroy,
    ):
        mock_rmtree, mock_workdir = self._destroy_mocks(
            monkeypatch,
            mock_workdir,
        )
        to_destroy_param = to_destroy
        if to_destroy is None:
            to_destroy = list(mock_workdir.prefixes.keys())

        assert mock_workdir.destroy(prefix_names=to_destroy_param) is None
        # we destroy all the specified prefixes
        for prefix_name in to_destroy:
            mock_workdir.get_prefix.assert_any_call(prefix_name)
            assert prefix_name not in mock_workdir.prefixes

        assert len(mock_workdir.get_prefix().method_calls) == len(to_destroy)
        # we did not destroy any others
        for prefix_name in mock_workdir.prefixes:
            with pytest.raises(AssertionError):
                mock_workdir.get_prefix.assert_any_call(prefix_name)
                assert prefix_name in mock_workdir.prefixes

        # we did not update anything
        if not to_destroy_param:
            return
        # we updated the current if there were any prefixes left
        if mock_workdir.prefixes:
            mock_workdir._update_current.assert_called_with()
        # if not, we removed the workdir
        else:
            mock_rmtree.assert_called_with(mock_workdir.path)

    @pytest.mark.parametrize(
        'workdir_parent,params,should_be_found',
        (
            (
                os.curdir,
                {
                    'start_path': 'auto'
                },
                True,
            ),
            (
                os.curdir,
                {},
                True,
            ),
            (
                '/one/two',
                {
                    'start_path': '/one/two/three'
                },
                True,
            ),
            (
                '/one',
                {
                    'start_path': '/one/two/three'
                },
                True,
            ),
            (
                'shrubbery',
                {
                    'start_path': '/one/two/three'
                },
                False,
            ),
        ),
        ids=(
            'auto uses curdir',
            'default uses curdir',
            'recurse one level',
            'recurse many levels',
            'not found',
        ),
    )
    def test_resolve_workdir_path_from_outside_of_it(
        self,
        workdir_parent,
        params,
        should_be_found,
    ):
        expected_result = os.path.abspath(
            os.path.join(workdir_parent, '.lago')
        )

        def is_workdir(path):
            return os.path.realpath(path) == expected_result

        mock_workdir_cls = mock.Mock(
            spec=lago.workdir.Workdir,
            is_workdir=is_workdir,
        )
        mock_workdir_cls.resolve_workdir_path = functools.partial(
            lago.workdir.Workdir.resolve_workdir_path.__func__,
            mock_workdir_cls,
        )

        if not should_be_found:
            with pytest.raises(LagoUserException):
                mock_workdir_cls.resolve_workdir_path(**params)
            return

        assert (
            mock_workdir_cls.resolve_workdir_path(**params) == expected_result
        )

    @pytest.mark.parametrize(
        'workdir_path,params,should_be_found',
        (
            (
                os.curdir,
                {
                    'start_path': 'auto'
                },
                True,
            ),
            (
                os.curdir,
                {},
                True,
            ),
            (
                'shrubbery',
                {
                    'start_path': '/one/two/three'
                },
                False,
            ),
        ),
        ids=(
            'auto uses curdir',
            'default uses curdir',
            'not found',
        ),
    )
    def test_resolve_workdir_path_from_inside_of_it(
        self,
        workdir_path,
        params,
        should_be_found,
    ):
        expected_result = os.path.abspath(workdir_path)

        def is_workdir(path):
            return os.path.realpath(path) == expected_result

        mock_workdir_cls = mock.Mock(
            spec=lago.workdir.Workdir,
            is_workdir=is_workdir,
        )
        mock_workdir_cls.resolve_workdir_path = functools.partial(
            lago.workdir.Workdir.resolve_workdir_path.__func__,
            mock_workdir_cls,
        )

        if not should_be_found:
            with pytest.raises(LagoUserException):
                mock_workdir_cls.resolve_workdir_path(**params)
            return

        assert (
            mock_workdir_cls.resolve_workdir_path(**params) == expected_result
        )

    def test_is_workdir_fails_if_load_raises_exception(self):
        def load(*args, **kwargs):
            raise lago.workdir.MalformedWorkdir()

        mock_workdir_cls = mock.Mock(spec=lago.workdir.Workdir)
        mock_workdir_cls().load = load
        mock_workdir_cls.is_workdir = functools.partial(
            lago.workdir.Workdir.is_workdir.__func__,
            mock_workdir_cls,
        )

        assert not mock_workdir_cls.is_workdir('shrubbery')
        mock_workdir_cls.assert_called_with(path='shrubbery')

    def test_is_workdir_ok_if_load_works(self, mock_workdir):
        mock_workdir_cls = mock.Mock(spec=lago.workdir.Workdir)
        mock_workdir_cls.is_workdir = functools.partial(
            lago.workdir.Workdir.is_workdir.__func__,
            mock_workdir_cls,
        )

        assert mock_workdir_cls.is_workdir('shrubbery')
        mock_workdir_cls.assert_called_with(path='shrubbery')
        mock_workdir_cls().load.assert_called_with()
