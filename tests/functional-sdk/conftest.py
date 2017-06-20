import os
import pytest
import shutil

_local_config = {
    'check_patch': {
        'images': ['el7.3-base']
    },
    'check_merged':
        {
            'images':
                [
                    'el7.3-base', 'el6-base', 'fc24-base', 'fc25-base',
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
    stage = pytest.config.getoption('--stage')
    if 'vm_name' in metafunc.fixturenames:
        metafunc.parametrize('vm_name', _stage_images(stage).keys())


def pytest_runtest_setup(item):
    stage = pytest.config.getoption('--stage')
    if item.get_marker('check_merged') and stage == 'check_patch':
        pytest.skip('runs only on check_merged stage')
    elif item.get_marker('check_patch') and stage == 'check_merged':
        pytest.skip('runs only on check_patch stage')


@pytest.fixture(scope='session')
def images(request):
    stage = pytest.config.getoption('--stage')
    return _stage_images(stage)


@pytest.fixture(scope='session')
def global_test_results():
    root_dir = os.environ.get('TEST_RESULTS', os.path.abspath('test_results'))
    workdir = os.path.abspath(os.path.join(root_dir, 'test_results_sdk'))
    if os.path.exists(workdir):
        shutil.rmtree(workdir)
    os.makedirs(workdir)
    return str(workdir)


@pytest.fixture(scope='module')
def tmp_workdir(tmpdir_factory):
    env_workdir = tmpdir_factory.mktemp('env')
    return env_workdir
