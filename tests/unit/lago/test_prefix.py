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
            prefix.DefaultPrefix.resolve_prefix_path('/')

    def test_curdir_is_prefix(self, tmpdir, monkeypatch):
        cur_paths = PathsMock(str(tmpdir))
        lagofile = tmpdir.join(os.path.basename(cur_paths.prefix_lagofile()))
        lagofile.write('')
        monkeypatch.setattr(lago.paths, 'Paths', PathsMock)
        result = prefix.DefaultPrefix.resolve_prefix_path(str(tmpdir))
        assert result == os.path.abspath(str(tmpdir))

    def test_curdir_has_prefix(self, tmpdir, local_prefix):
        result = prefix.DefaultPrefix.resolve_prefix_path(str(tmpdir))
        assert result == os.path.abspath(str(local_prefix))

    def test_parent_has_prefix(self, tmpdir, local_prefix):
        sub_dir = tmpdir.mkdir('subdir')
        result = prefix.DefaultPrefix.resolve_prefix_path(str(sub_dir))
        assert result == os.path.abspath(str(local_prefix))

    def test_many_parent_has_prefix(self, tmpdir, local_prefix):
        sub_dir = tmpdir.mkdir('subdir')
        subsub_dir = sub_dir.mkdir('subsubdir')
        result = prefix.DefaultPrefix.resolve_prefix_path(str(subsub_dir))
        assert result == os.path.abspath(str(local_prefix))
