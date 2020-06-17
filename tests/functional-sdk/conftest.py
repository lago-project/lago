from __future__ import absolute_import

import os
import pytest
import shutil
from lago_fixtures import (  # noqa: F401
    tmp_workdir, init_dict, init_fname, test_results,
    external_log, env, vms, nets
)

_local_config = {
    'check_patch': {
        'images': ['el7.6-base-2']
    },
    'check_merged':
        {
            'images':
                [
                    'el7.6-base-2', 'el6-base', 'fc28-base', 'fc29-base',
                    'ubuntu16.04-base', 'debian8-base'
                ]
        }  # noqa: E123
}


def _stage_images(stage):
    return {
        'vm-{0}'.format(image.replace('.', '-')): image
        for image in _local_config[stage]['images']
    }


def pytest_addoption(parser):
    parser.addoption(
        '--stage',
        action='store',
        default='check_patch',
        help='standard-ci stage: check_patch/check_merged'
    )


def pytest_generate_tests(metafunc):
    if 'vm_name' in metafunc.fixturenames:
        metafunc.parametrize(
            'vm_name',
            _stage_images(metafunc.config.option.stage).keys()
        )


def pytest_runtest_setup(item):
    stage = item.config.option.stage
    if item.get_closest_marker('check_merged') and stage == 'check_patch':
        pytest.skip('runs only on check_merged stage')
    elif item.get_closest_marker('check_patch') and stage == 'check_merged':
        pytest.skip('runs only on check_patch stage')


@pytest.fixture(scope='session')
def images(request):
    return _stage_images(request.config.option.stage)


@pytest.fixture(scope='session')
def global_test_results():
    root_dir = os.environ.get('TEST_RESULTS', os.path.abspath('test_results'))
    workdir = os.path.abspath(os.path.join(root_dir, 'test_results_sdk'))
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    os.makedirs(workdir)
    return str(workdir)
