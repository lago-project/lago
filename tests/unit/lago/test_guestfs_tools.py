import pytest
from mock import call, patch
from lago import guestfs_tools
from lago.plugins.vm import ExtractPathNoPathError
from lago.guestfs_tools import GuestFSError
from random import shuffle

# An alternative approach to 'MockGuestFS' class would have been using mock's
# autospec, i.e.:
# @pytest.fixture
#   def mock_gfs():
#        with patch(
#            'lago.guestfs_tools.guestfs.GuestFS', autospec=True
#        ) as mocked:
#            yield mocked
# But, turns out 'autospec' in this case is extremely slow(around 1 second
# for each test).
# see: https://docs.python.org/3/library/unittest.mock.html#autospeccing
# for possible reasons(probably dynamic code execution).


class MockGuestFS(object):
    def inspect_os(self):
        pass

    def list_filesystems(self):
        pass

    def mount_ro(self):
        pass

    def umount(self):
        pass

    def add_drive_ro(self):
        pass

    def set_backend(self):
        pass

    def launch(self):
        pass

    def shutdown(self):
        pass

    def close(self):
        pass

    def download(self):
        pass

    def is_file(self):
        pass

    def is_dir(self):
        pass

    def copy_out(self):
        pass


@pytest.fixture
def mock_gfs():
    with patch(
        'lago.guestfs_tools.guestfs.GuestFS', spec=MockGuestFS
    ) as mocked:
        yield mocked


@pytest.fixture
def mock_gfs_fs(mock_gfs):
    mock_gfs.return_value.inspect_os.return_value = ['/dev/sda1']
    return mock_gfs.return_value


class TestGuestFSTools(object):
    @pytest.mark.parametrize(
        'filesystems,root_device', [
            ({
                '/dev/sdb': ''
            }, '/dev/sdb'), (
                {
                    '/dev/sdb': '',
                    '/dev/sdz': '',
                    '/dev/vda': '',
                    '/dev/sdr': ''
                }, '/dev/sdz'
            )
        ]
    )
    def test_find_rootfs_fullname(self, mock_gfs, filesystems, root_device):
        mock_gfs.inspect_os.return_value = []
        mock_gfs.list_filesystems.return_value = filesystems
        res = guestfs_tools.find_rootfs(mock_gfs, root_device)
        mock_gfs.list_filesystems.assert_called()
        assert res == root_device

    @pytest.mark.parametrize(
        'filesystems,root_device,expected', [
            ({
                '/a/dev/sda': ''
            }, '/dev/sda', '/a/dev/sda'),
            ({
                '/dev/sdb': '',
                '/path/to/sdz': ''
            }, 'sdz', '/path/to/sdz')
        ]
    )
    def test_find_rootfs_substring(
        self, mock_gfs, filesystems, root_device, expected
    ):
        mock_gfs.inspect_os.return_value = []
        mock_gfs.list_filesystems.return_value = filesystems
        res = guestfs_tools.find_rootfs(mock_gfs, root_device)
        mock_gfs.list_filesystems.assert_called()
        assert res == expected

    def test_find_rootfs_empty(self, mock_gfs):
        mock_gfs.inspect_os.return_value = []
        mock_gfs.list_filesystems.return_value = {}
        with pytest.raises(GuestFSError):
            guestfs_tools.find_rootfs(mock_gfs, '/dev/sda')
        mock_gfs.list_filesystems.assert_called()

    @pytest.mark.parametrize(
        'filesystems,root_device', [
            ({}, 'abc'),
            ({
                '/dev/sda': ''
            }, '/dev/sdb'),
        ]
    )
    def test_find_rootfs_raises(self, mock_gfs, filesystems, root_device):
        mock_gfs.inspect_os.return_value = []
        mock_gfs.list_filesystems.return_value = filesystems
        with pytest.raises(GuestFSError):
            guestfs_tools.find_rootfs(mock_gfs, root_device)
        mock_gfs.list_filesystems.assert_called()

    def test_guestfs_conn_ro_fallback_backend(self, mock_gfs):
        with guestfs_tools.guestfs_conn_ro(disk='dummy') as conn:
            assert conn.set_backend.call_args == call('direct')

    def test_guestfs_conn_ro_env_backend(self, monkeypatch, mock_gfs):
        monkeypatch.setenv('LIBGUESTFS_BACKEND', 'libvirt')
        with guestfs_tools.guestfs_conn_ro(disk='dummy') as conn:
            assert conn.set_backend.call_args == call('libvirt')

    def test_guestfs_conn_ro_expand_vars(self, mock_gfs, monkeypatch):
        expanded_path = '/some/path'
        monkeypatch.setenv('SOME_PATH', expanded_path)
        with guestfs_tools.guestfs_conn_ro(disk='$SOME_PATH/file') as conn:
            assert conn.add_drive_ro.call_args == call('/some/path/file')

    def test_guestfs_conn_ro_expand_wrong_var(self, mock_gfs, monkeypatch):
        monkeypatch.delenv('SOME_PATH', raising=False)
        with guestfs_tools.guestfs_conn_ro(disk='$SOME_PATH/file') as conn:
            assert conn.add_drive_ro.call_args == call('$SOME_PATH/file')

    def test_guestfs_conn_ro_teardown(self, mock_gfs):
        with guestfs_tools.guestfs_conn_ro(disk='dummy') as conn:
            pass
        assert call.add_drive_ro('dummy') in conn.mock_calls
        assert conn.mock_calls[-1] == call.close()
        assert conn.mock_calls[-2] == call.shutdown()

    def test_guestfs_conn_ro_error(self, mock_gfs):
        mock_gfs.return_value.launch.side_effect = RuntimeError('mocking')
        with pytest.raises(guestfs_tools.GuestFSError):
            with guestfs_tools.guestfs_conn_ro(disk='dummy'):
                pass

    @pytest.mark.parametrize(
        'disk_path,disk_root', [('/path/to/file.qcow', '/dev/sda')]
    )
    def test_guestfs_conn_mount_ro(self, mock_gfs, disk_path, disk_root):
        with patch('lago.guestfs_tools.find_rootfs') as mock_rootfs:
            mock_rootfs.return_value = disk_root
            with guestfs_tools.guestfs_conn_mount_ro(
                disk_path, disk_root
            ) as conn:
                assert call.mount_ro(disk_root, '/') in conn.mock_calls
                assert call.add_drive_ro(disk_path) in conn.mock_calls
                conn.mount_ro.assert_called_once()
                conn.add_drive_ro.assert_called_once()
                mock_rootfs.assert_called_once()
            mock_gfs.return_value.umount.assert_called_once()

    @pytest.mark.parametrize(
        'disk_path,disk_root', [('/path/to/file.qcow', '/dev/sda')]
    )
    @pytest.mark.parametrize('retries', [1, 3, 13])
    def test_guestfs_conn_mount_ro_retries(
        self, mock_gfs, disk_path, disk_root, retries
    ):
        side_effects = [RuntimeError()] * (retries - 1)
        side_effects.append(None)
        mock_gfs.return_value.mount_ro.side_effect = side_effects
        with patch('lago.guestfs_tools.find_rootfs') as mock_rootfs:
            mock_rootfs.return_value = disk_root
            with guestfs_tools.guestfs_conn_mount_ro(
                disk_path, disk_root, retries=retries, wait=0
            ) as conn:

                assert call.mount_ro(disk_root, '/') in conn.mock_calls
                assert call.add_drive_ro(disk_path) in conn.mock_calls
            assert conn.mount_ro.call_count == retries
            assert conn.umount.call_count == 1
            assert conn.add_drive_ro.call_count == retries
            assert conn.shutdown.call_count == retries
            assert conn.close.call_count == retries

    @pytest.mark.parametrize(
        'disk_path,disk_root', [('/path/to/file.qcow', '/dev/sda')]
    )
    @pytest.mark.parametrize('retries', [1, 3])
    def test_guestfs_conn_mount_ro_retries_raises(
        self, mock_gfs, disk_path, disk_root, retries
    ):
        side_effects = [RuntimeError()] * (retries)
        mock_gfs.return_value.mount_ro.side_effect = side_effects
        with patch('lago.guestfs_tools.find_rootfs') as mock_rootfs:
            mock_rootfs.return_value = disk_root
            with pytest.raises(GuestFSError):
                with guestfs_tools.guestfs_conn_mount_ro(
                    disk_path, disk_root, retries=retries, wait=0
                ):
                    pass

            assert mock_gfs.return_value.mount_ro.call_count == retries
            assert mock_gfs.return_value.umount.call_count == 0
            assert mock_gfs.return_value.add_drive_ro.call_count == retries
            assert mock_gfs.return_value.shutdown.call_count == retries
            assert mock_gfs.return_value.close.call_count == retries

    @pytest.mark.parametrize(
        'disk_path,disk_root', [('/path/to/file.qcow', '/dev/sda')]
    )
    def test_guestfs_conn_mount_ro_umount_raises(
        self, mock_gfs, disk_path, disk_root
    ):
        mock_gfs.return_value.umount.side_effect = RuntimeError()
        with patch('lago.guestfs_tools.find_rootfs') as mock_rootfs:
            mock_rootfs.return_value = disk_path
            with pytest.raises(GuestFSError):
                with guestfs_tools.guestfs_conn_mount_ro(disk_path, disk_root):
                    pass
            assert mock_gfs.return_value.umount.call_count == 1
            assert mock_gfs.return_value.mount_ro.call_count == 1

    @pytest.mark.parametrize(
        'files,dirs', [
            (
                [
                    ('file_src{0}'.format(idx), 'file_dst{0}'.format(idx))
                    for idx in range(9)
                ], [
                    ('dir_src{0}'.format(idx), 'dir_dst{0}'.format(idx))
                    for idx in range(9)
                ]
            ),
            ([], [('dir1', 'dirdst1')]),
            ([('src1', 'dst1')], []),
            ([], []),
        ]
    )
    def test_extract_paths_files_dirs(self, files, dirs, mock_gfs_fs):
        def mock_is_file(fname, **kwargs):
            return len([src for src, _ in files if src == fname]) == 1

        def mock_is_dir(dname, **kwargs):
            return len([src for src, _ in dirs if src == dname]) == 1

        joined = files + dirs
        shuffle(joined)

        with patch('lago.guestfs_tools.os.path.isdir') as mock_path_isdir:
            with patch('lago.guestfs_tools.os.makedirs'):
                mock_path_isdir.return_value = True
                mock_gfs_fs.is_file.side_effect = mock_is_file
                mock_gfs_fs.is_dir.side_effect = mock_is_dir
                guestfs_tools.extract_paths(
                    'a', 'b', joined, ignore_nopath=False
                )
                assert sorted(mock_path_isdir.mock_calls) == sorted(
                    [call(host_path) for _, host_path in dirs]
                )

                assert sorted(mock_gfs_fs.download.mock_calls) == sorted(
                    [
                        call(guest_path, host_path)
                        for guest_path, host_path in files
                    ]
                )
                assert sorted(mock_gfs_fs.copy_out.mock_calls) == sorted(
                    [
                        call(guest_path, host_path)
                        for guest_path, host_path in dirs
                    ]
                )

    def test_extract_paths_nodir_created(self, mock_gfs_fs):
        with patch('lago.guestfs_tools.os.path.isdir') as mock_path_isdir:
            with patch('lago.guestfs_tools.os.makedirs') as mock_makedirs:
                mock_path_isdir.return_value = False
                mock_gfs_fs.is_file.return_value = False
                mock_gfs_fs.is_dir.return_value = True
                guestfs_tools.extract_paths(
                    'a', 'b', [('src-dir', 'dst-dir')], ignore_nopath=False
                )
                assert mock_makedirs.mock_calls == [call('dst-dir')]

    def test_extract_paths_file_raises(self, mock_gfs_fs):
        with patch('lago.guestfs_tools.os.path.isdir') as mock_path_isdir:
            with patch('lago.guestfs_tools.os.makedirs'):
                mock_path_isdir.return_value = False
                mock_gfs_fs.is_file.return_value = True
                mock_gfs_fs.download.side_effect = RuntimeError('mock')
                with pytest.raises(GuestFSError):
                    guestfs_tools.extract_paths(
                        'a',
                        'b', [('src-dir', 'dst-dir')],
                        ignore_nopath=False
                    )

                assert mock_gfs_fs.download.call_count == 1

    def test_extract_paths_dir_raises(self, mock_gfs_fs):
        with patch('lago.guestfs_tools.os.path.isdir') as mock_path_isdir:
            with patch('lago.guestfs_tools.os.makedirs'):
                mock_path_isdir.return_value = True
                mock_gfs_fs.is_file.return_value = False
                mock_gfs_fs.copy_out.side_effect = RuntimeError('mock')
                with pytest.raises(GuestFSError):
                    guestfs_tools.extract_paths(
                        'a',
                        'b', [('src-dir', 'dst-dir')],
                        ignore_nopath=False
                    )
                assert mock_gfs_fs.copy_out.call_count == 1

    def test_extract_paths_no_file_guest_skipped(self, mock_gfs_fs):
        with patch('lago.guestfs_tools.os.path.isdir') as mock_path_isdir:
            with patch('lago.guestfs_tools.os.makedirs'):
                mock_path_isdir.return_value = False
                mock_gfs_fs.is_file.return_value = False
                mock_gfs_fs.is_dir.return_value = False
                guestfs_tools.extract_paths(
                    'a', 'b', [('src', 'dst')], ignore_nopath=True
                )
                assert mock_gfs_fs.is_file.call_count == 1
                assert mock_gfs_fs.is_dir.call_count == 1

    def test_extract_paths_no_file_guest_raises(self, mock_gfs_fs):
        with patch('lago.guestfs_tools.os.path.isdir') as mock_path_isdir:
            with patch('lago.guestfs_tools.os.makedirs'):
                mock_path_isdir.return_value = False
                mock_gfs_fs.is_file.return_value = False
                mock_gfs_fs.is_dir.return_value = False
                with pytest.raises(ExtractPathNoPathError):
                    guestfs_tools.extract_paths(
                        'a', 'b', [('src', 'dst')], ignore_nopath=False
                    )
                assert mock_gfs_fs.is_file.call_count == 1
                assert mock_gfs_fs.is_dir.call_count == 1
