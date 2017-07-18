import json
import yaml
from StringIO import StringIO

from lago import utils

import pytest


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


# yapf: disable
class TestDeepUpdate(object):
    @pytest.mark.parametrize(
        'a, b, expected',
        [
            (
                {
                    'run_cmd': [1, 2]
                },
                {
                    'run_cmd': [3, 4]
                },
                {
                    'run_cmd': [1, 2, 3, 4]
                }
            ),
            (
                {
                    'run_cmd_1': [1, 2],
                    'run_cmd_2': ['a,', 'b']
                },
                {
                    'run_cmd_1': [3, 4]
                },
                {
                    'run_cmd_1': [1, 2, 3, 4],
                    'run_cmd_2': ['a,', 'b']
                }
            ),
            (
                {
                    'run_cmd_1': {
                        'aa': [1, 2],
                        'bb': 100
                    },
                    'run_cmd_2': {
                        'a': 1,
                        'b': 2
                    }
                },
                {
                    'run_cmd_1': {
                        'aa': [3, 4],
                        'bb': 'hi'
                    },
                    'run_cmd_2': {
                        'a': 10,
                        'c': 3
                    }
                },
                {
                    'run_cmd_1': {
                        'aa': [1, 2, 3, 4],
                        'bb': 'hi'
                    },
                    'run_cmd_2': {
                        'a': 10,
                        'b': 2,
                        'c': 3
                    }
                }
            ),
            (
                {}, {}, {}
            ),
            (
                {
                    'run_cmd_1': {
                        'a': {
                            'a': 1,
                            'c': None
                        }
                    },
                    'run_cmd_2': [1, 2]
                },
                {
                    'run_cmd_2': [3, 4],
                    'run_cmd_1': {
                        'a': {
                            'a': 'a',
                            'b': 'b'
                        }
                    },
                    'run_cmd_3': 'a'
                },
                {
                    'run_cmd_1': {
                        'a': {
                            'a': 'a',
                            'b': 'b',
                            'c': None
                        }
                    },
                    'run_cmd_2': [1, 2, 3, 4],
                    'run_cmd_3': 'a'
                }
            )
        ]
    )
    def test_deep_update(self, a, b, expected):
        result = utils.deep_update(a, b)
        assert deep_compare(result, expected)

    @pytest.mark.parametrize(
        'a, b',
        [
            ({}, []),
            ('a', {}),
            ([], [])
        ]
    )
    def test_deep_update_not_supported_types(self, a, b):
        with pytest.raises(utils.LagoException):
            utils.deep_update(a, b)

# yapf: enable
