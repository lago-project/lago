import json
import os
import yaml

from six import StringIO

import pytest

from lago import utils


def deep_compare(original_obj, copy_obj):
    assert copy_obj == original_obj
    if isinstance(original_obj, list):
        assert copy_obj is not original_obj
        for orig_elem, copy_elem in zip(original_obj, copy_obj):
            assert deep_compare(orig_elem, copy_elem)

    if isinstance(original_obj, dict):
        assert copy_obj is not original_obj
        assert len(original_obj.keys()) == len(copy_obj.keys())
        for key in original_obj.keys():
            assert original_obj[key] == copy_obj[key]
            assert deep_compare(original_obj[key], copy_obj[key])

    return True


class TestDeepCopy(object):
    def test_non_dict_object(self):
        base_object = 'dummy string'
        copied_object = utils.deepcopy(base_object)
        assert copied_object == base_object

    def test_plain_dict(self):
        base_object = {'dummy_elem': 123}
        copied_object = utils.deepcopy(base_object)
        assert deep_compare(base_object, copied_object)

    def test_plain_list(self):
        base_object = ['dummy_elem', 123]
        copied_object = utils.deepcopy(base_object)
        assert deep_compare(base_object, copied_object)

    def test_nested_list(self):
        base_object = [['dummy_elem', 123], 234]
        copied_object = utils.deepcopy(base_object)
        assert deep_compare(base_object, copied_object)

    def test_nested_dict(self):
        base_object = {'dummy_elem': {'dummy_elem2': 123}}
        copied_object = utils.deepcopy(base_object)
        assert deep_compare(base_object, copied_object)

    def test_nested_mixed(self):
        base_object = {
            'dummy_elem': [123],
            'dummy_dict': {
                'dummy_list': [123],
                'dummy_int': 234,
            },
        }

        copied_object = utils.deepcopy(base_object)
        assert deep_compare(base_object, copied_object)


class TestLoadVirtStream(object):
    virt_conf = {
        'domains':
            [
                {
                    'domain01':
                        {
                            'disks': [
                                {
                                    'name': 'disk1'
                                },
                                {
                                    'name': 'disk2'
                                },
                            ]
                        },
                    'domain02':
                        {
                            'disks': [
                                {
                                    'name': 'disk1'
                                },
                                {
                                    'name': 'disk2'
                                },
                            ]
                        }
                }
            ]
    }

    def test_load_yaml(self):
        yaml_fd = StringIO(yaml.dump(self.virt_conf))
        loaded_conf = utils.load_virt_stream(virt_fd=yaml_fd)
        assert deep_compare(self.virt_conf, loaded_conf)

    def test_load_json(self):
        json_fd = StringIO(json.dumps(self.virt_conf))
        loaded_conf = utils.load_virt_stream(virt_fd=json_fd)
        assert deep_compare(self.virt_conf, loaded_conf)

    def test_fallback_to_yaml(self):
        bad_json = StringIO("{'one': 1,}")
        expected = {'one': 1}
        loaded_conf = utils.load_virt_stream(virt_fd=bad_json)
        assert deep_compare(expected, loaded_conf)


def test_should_give_a_temporary_directory_in():
    remembered_dir_path = None
    remembered_file_path = None

    with utils.TemporaryDirectory() as tmpdir_path:
        remembered_dir_path = tmpdir_path

        assert os.path.isdir(tmpdir_path)

        some_file_path = os.path.join(tmpdir_path, "smth")
        remembered_file_path = some_file_path

        with open(some_file_path, "w") as some_file:
            some_file.write("stuff")
        assert os.path.isfile(some_file_path)

    assert not os.path.exists(remembered_dir_path)
    assert not os.path.exists(remembered_file_path)


def test_temporary_directory_should_respect_ignoring_errors_in():
    with utils.TemporaryDirectory(ignore_errors=True) as tmpdir_path:
        os.rmdir(tmpdir_path)
        assert not os.path.exists(tmpdir_path)

    with pytest.raises(OSError):
        with utils.TemporaryDirectory(ignore_errors=False) as tmpdir_path:
            os.rmdir(tmpdir_path)
