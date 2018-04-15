import logging
import os
import shutil
import tempfile
import pytest
import yaml
from lago import sdk


@pytest.fixture(scope='module')
def tmp_workdir(tmpdir_factory):
    env_workdir = tmpdir_factory.mktemp('env')
    return env_workdir


@pytest.fixture(scope='module')
def init_dict(init_str):
    return yaml.load(init_str)


@pytest.fixture(scope='module')
def init_fname(init_str):
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(init_str)
    return f.name


@pytest.fixture(scope='module')
def test_results(request, global_test_results):
    results_path = os.path.join(
        global_test_results, str(request.module.__name__)
    )
    os.makedirs(results_path)
    return results_path


@pytest.fixture(scope='module')
def external_log(tmpdir_factory):
    return tmpdir_factory.mktemp('external_log').join('custom_log.log')


@pytest.fixture(scope='module', autouse=True)
def env(request, init_fname, test_results, tmp_workdir, external_log):
    workdir = os.path.join(str(tmp_workdir), 'lago')
    env = sdk.init(
        init_fname,
        workdir=workdir,
        logfile=str(external_log),
        loglevel=logging.DEBUG,
    )
    env.start()
    try:
        yield env
        collect_path = os.path.join(test_results, 'collect')
        env.collect_artifacts(output_dir=collect_path, ignore_nopath=True)
        shutil.copytree(
            workdir,
            os.path.join(test_results, 'workdir'),
            ignore=shutil.ignore_patterns('*images*')
        )
    finally:
        env.stop()
        env.destroy()


@pytest.fixture(scope='module')
def vms(env):
    return env.get_vms()


@pytest.fixture(scope='module')
def nets(env):
    return env.get_nets()
