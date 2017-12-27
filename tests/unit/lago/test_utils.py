import json
import yaml
from StringIO import StringIO

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
