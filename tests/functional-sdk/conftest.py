import os
import pytest
import shutil


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
    return str(env_workdir)
