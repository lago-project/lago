from functools import partial
import logging
from os import path
import yaml
from textwrap import dedent
from jinja2 import Environment, PackageLoader

import log_utils
import utils

LOGGER = logging.getLogger(__name__)
LogTask = partial(log_utils.LogTask, logger=LOGGER)


def generate_from_itr(
    vms, iso_dir, ssh_public_key, collect_only=False, with_threads=False
):
    with LogTask('Creating cloud-init iso images'):
        utils.safe_mkdir(iso_dir)
        handlers = [
            partial(
                generate,
                vm,
                iso_dir,
                ssh_public_key,
                collect_only,
            ) for vm in vms
        ]

        if with_threads:
            iso_path = utils.invoke_different_funcs_in_parallel(*handlers)
        else:
            iso_path = [handler() for handler in handlers]

    return dict(iso_path)


def generate(vm, iso_dir, ssh_public_key, collect_only=False):
    # Verify that the spec is not None
    vm_name = vm.name()

    with LogTask('Creating cloud-init iso for {}'.format(vm_name)):
        cloud_spec = vm.spec['cloud-init']

        vm_iso_dir = path.join(iso_dir, vm_name)
        utils.safe_mkdir(vm_iso_dir)

        vm_iso_path = path.join(iso_dir, '{}.iso'.format(vm_name))

        normalized_spec = normalize_spec(
            cloud_spec,
            get_jinja_replacements(vm, ssh_public_key),
            vm.distro(),
        )

        LOGGER.debug(normalized_spec)

        if not collect_only:
            write_to_iso = []
            user_data = normalized_spec.pop('user-data')
            if user_data:
                user_data_dir = path.join(vm_iso_dir, 'user-data')
                write_yaml_to_file(
                    user_data,
                    user_data_dir,
                    prefix_lines=['#cloud-config', '\n']
                )
                write_to_iso.append(user_data_dir)

            for spec_type, spec in normalized_spec.viewitems():
                out_dir = path.join(vm_iso_dir, spec_type)
                write_yaml_to_file(spec, out_dir)
                write_to_iso.append(out_dir)

            if write_to_iso:
                gen_iso_image(vm_iso_path, write_to_iso)
            else:
                LOGGER.debug('{}: no specs were found'.format(vm_name))
        else:
            print yaml.safe_dump(normalized_spec)

    iso_spec = vm_name, vm_iso_path

    return iso_spec


def get_jinja_replacements(vm, ssh_public_key):
    # yapf: disable
    return {
        'user-data': {
            'root_password': vm.root_password(),
            'public_key': ssh_public_key,
        },
        'meta-data': {
            'hostname': vm.name(),
        },
    }
# yapf: enable


def normalize_spec(cloud_spec, defaults, vm_distro):
    """
    For all spec type in 'jinja_replacements', load the default and user
    given spec and merge them.

    Returns:
        dict: the merged default and user spec
    """
    normalized_spec = {}

    for spec_type, mapping in defaults.viewitems():
        normalized_spec[spec_type] = utils.deep_update(
            load_default_spec(spec_type, vm_distro, **mapping),
            load_given_spec(cloud_spec.get(spec_type, {}), spec_type)
        )

    return normalized_spec


def load_given_spec(given_spec, spec_type):
    """
    Load spec_type given from the user.
    If 'path' is in the spec, the file will be loaded from 'path',
    otherwise the spec will be returned without a change.

    Args:
        dict or list: which represents the spec
        spec_type(dict): the type of the spec

    Returns:
        dict or list: which represents the spec
    """
    if not given_spec:
        LOGGER.debug('{} spec is empty'.format(spec_type))
        return given_spec

    if 'path' in given_spec:
        LOGGER.debug(
            'loading {} spec from {}'.format(spec_type, given_spec['path'])
        )
        return load_spec_from_file(given_spec['path'])


def load_default_spec(spec_type, vm_distro, **kwargs):
    """
    Load default spec_type template from lago.templates
    and render it with jinja2

    Args:
        spec_type(dict): the type of the spec
        kwargs(dict): k, v for jinja2

    Returns:
        dict or list: which represnets the spec
    """

    jinja_env = Environment(loader=PackageLoader('lago', 'templates'))
    template_name = 'cloud-init-{}-{}.j2'.format(spec_type, vm_distro)
    base_template_name = 'cloud-init-{}-base.j2'.format(spec_type)
    template = jinja_env.select_template([template_name, base_template_name])

    default_spec = template.render(**kwargs)
    LOGGER.debug('default spec for {}:\n{}'.format(spec_type, default_spec))

    return yaml.safe_load(default_spec)


def load_spec_from_file(path_to_file):
    try:
        with open(path_to_file, mode='rt') as f:
            return yaml.safe_load(f)
    except yaml.YAMLError:
        raise LagoCloudInitParseError(path_to_file)


def write_yaml_to_file(spec, out_dir, prefix_lines=None, suffix_lines=None):
    with open(out_dir, mode='wt') as f:
        if prefix_lines:
            f.writelines(prefix_lines)
        yaml.safe_dump(spec, f)
        if suffix_lines:
            f.writelines(suffix_lines)


def gen_iso_image(out_file_name, files):
    cmd = [
        'genisoimage',
        '-output',
        out_file_name,
        '-volid',
        'cidata',
        '-joliet',
        '-rock',
    ]

    cmd.extend(files)
    utils.run_command_with_validation(cmd)


class LagoCloudInitException(utils.LagoException):
    pass


class LagoCloudInitParseError(LagoCloudInitException):
    def __init__(self, file_path):
        super(LagoCloudInitParseError, self).__init__(
            dedent(
                """
                    Failed to parse yaml file {}.
                    """.format(file_path)
            )
        )
