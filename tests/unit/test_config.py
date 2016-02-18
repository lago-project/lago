import contextlib
import functools
import os
import shutil
import tempfile

import pytest

import lago.config as config

_ENV = {'LAGO_ENV_VAR_1': 'env_val_1', 'LAGO_USER_VAR_1': 'env_val_2', }

_USER_CONF = '''
[lago]
user_var_1 = user_val_1
user_var_2 = user_val_2
system_var_3 = user_val_3
'''

_SYSTEM_CONF_1 = '''
[lago]
system_var_1 = system_val_1
'''

_SYSTEM_CONF_2 = '''
[lago]
system_var_2 = system_val_2
system_var_3 = system_val_3
'''


@contextlib.contextmanager
def tempdir(prefix='/tmp/'):
    path = tempfile.mkdtemp(prefix=prefix)
    try:
        yield path
    finally:
        shutil.rmtree(path)


@contextlib.contextmanager
def monkey_patch(obj, subs):
    stash = {}
    for k, v in subs.items():
        stash[k] = getattr(obj, k)
        setattr(obj, k, v)

    try:
        yield obj
    finally:
        for k, v in stash.items():
            setattr(obj, k, v)


@contextlib.contextmanager
def config_context():
    with tempdir() as tmp:

        def mkpath(path):
            return os.path.join(tmp, path)

        for dest, conts in [
            ('.userconf', _USER_CONF),
            ('test1.conf', _SYSTEM_CONF_1),
            ('test2.conf', _SYSTEM_CONF_2),
        ]:
            with open(mkpath(dest), 'w') as f:
                f.write(conts)

        with monkey_patch(
            config,
            {
                '_cache': {},
                '_get_environ': lambda: _ENV,
                '_SYSTEM_CONFIG_DIR': tmp,
                '_USER_CONFIG': mkpath('.userconf'),
            },
        ):
            yield


def _config_test(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with config_context():
            return func(*args, **kwargs)

    return wrapper


@_config_test
def test_nonexistent_throws():
    with pytest.raises(KeyError):
        config.get('i_dont_exist')


@_config_test
def test_nonexistent_default():
    assert config.get('i_dont_exist', 'foo') == 'foo'


@_config_test
def test_get_from_env():
    assert config.get('env_var_1') == 'env_val_1'


@_config_test
def test_env_shadows_user():
    assert config.get('user_var_1') == 'env_val_2'


@_config_test
def test_get_from_user():
    assert config.get('user_var_2') == 'user_val_2'


@_config_test
def test_user_shadows_system():
    assert config.get('system_var_3') == 'user_val_3'


@_config_test
def test_get_from_system():
    assert config.get('system_var_1') == 'system_val_1'
    assert config.get('system_var_2') == 'system_val_2'
