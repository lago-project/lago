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
import os

import pytest

import lago
from lago import prefix


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
            prefix.resolve_prefix_path('/')

    def test_curdir_is_prefix(self, tmpdir, monkeypatch):
        cur_paths = PathsMock(str(tmpdir))
        lagofile = tmpdir.join(os.path.basename(cur_paths.prefix_lagofile()))
        lagofile.write('')
        monkeypatch.setattr(lago.paths, 'Paths', PathsMock)
        result = prefix.resolve_prefix_path(str(tmpdir))
        assert result == os.path.abspath(str(tmpdir))

    def test_curdir_has_prefix(self, tmpdir, local_prefix):
        result = prefix.resolve_prefix_path(str(tmpdir))
        assert result == os.path.abspath(str(local_prefix))

    def test_parent_has_prefix(self, tmpdir, local_prefix):
        sub_dir = tmpdir.mkdir('subdir')
        result = prefix.resolve_prefix_path(str(sub_dir))
        assert result == os.path.abspath(str(local_prefix))

    def test_many_parent_has_prefix(self, tmpdir, local_prefix):
        sub_dir = tmpdir.mkdir('subdir')
        subsub_dir = sub_dir.mkdir('subsubdir')
        result = prefix.resolve_prefix_path(str(subsub_dir))
        assert result == os.path.abspath(str(local_prefix))
