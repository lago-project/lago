#
# Copyright 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
import Queue
import collections
import datetime
import fcntl
import functools
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import yaml

import lockfile

from . import constants
from .log_utils import (LogTask, setup_prefix_logging)

LOGGER = logging.getLogger(__name__)


class TimerException(Exception):
    """
    Exception to throw when a timeout is reached
    """
    pass


def _ret_via_queue(func, queue):
    try:
        queue.put({'return': func()})
    except Exception:
        LOGGER.exception('Error while running thread')
        queue.put({'exception': sys.exc_info()})


def func_vector(target, args_sequence):
    return [functools.partial(target, *args) for args in args_sequence]


class VectorThread:
    def __init__(self, targets):
        self.targets = targets
        self.results = None

    def start_all(self):
        self.thread_handles = []
        for target in self.targets:
            q = Queue.Queue()
            t = threading.Thread(target=_ret_via_queue, args=(target, q))
            self.thread_handles.append((t, q))
            t.start()

    def join_all(self, raise_exceptions=True):
        if self.results:
            return self.results

        for t, q in self.thread_handles:
            t.join()

        self.results = map(lambda (t, q): q.get(), self.thread_handles)
        if raise_exceptions:
            for result in self.results:
                if 'exception' in result:
                    exc_info = result['exception']
                    raise exc_info[1], None, exc_info[2]
        return map(lambda x: x.get('return', None), self.results)


def invoke_in_parallel(func, *args_sequences):
    vt = VectorThread(func_vector(func, zip(*args_sequences)))
    vt.start_all()
    vt.join_all()


_CommandStatus = collections.namedtuple(
    'CommandStatus', ('code', 'out', 'err')
)


class CommandStatus(_CommandStatus):
    def __nonzero__(self):
        return self.code


def _run_command(
    command,
    input_data=None,
    stdin=None,
    out_pipe=subprocess.PIPE,
    err_pipe=subprocess.PIPE,
    env=None,
    **kwargs
):
    """
    Runs a command

    Args:
        command(list of str): args of the command to execute, including the
            command itself as command[0] as `['ls', '-l']`
        input_data(str): If passed, will feed that data to the subprocess
            through stdin
        out_pipe(int or file): File descriptor as passed to
            :ref:subprocess.Popen to use as stdout
        stdin(int or file): File descriptor as passed to
            :ref:subprocess.Popen to use as stdin
        err_pipe(int or file): File descriptor as passed to
            :ref:subprocess.Popen to use as stderr
        env(dict of str:str): If set, will use the given dict as env for the
            subprocess
        **kwargs: Any other keyword args passed will be passed to the
            :ref:subprocess.Popen call

    Returns:
        lago.utils.CommandStatus: result of the interactive execution
    """
    # add libexec to PATH if needed
    if constants.LIBEXEC_DIR not in os.environ['PATH'].split(':'):
        os.environ['PATH'] = '%s:%s' % (
            constants.LIBEXEC_DIR, os.environ['PATH']
        )

    if input_data and not stdin:
        kwargs['stdin'] = subprocess.PIPE
    elif stdin:
        kwargs['stdin'] = stdin

    if env is None:
        env = os.environ.copy()
    else:
        env['PATH'] = ':'.join(
            list(
                set(
                    env.get('PATH', '').split(':') + os.environ[
                        'PATH'
                    ].split(':')
                ),
            ),
        )

    popen = subprocess.Popen(
        ' '.join('"%s"' % arg for arg in command),
        stdout=out_pipe,
        stderr=err_pipe,
        shell=True,
        env=env,
        **kwargs
    )
    out, err = popen.communicate(input_data)
    LOGGER.debug('command exit with %d', popen.returncode)
    if out:
        LOGGER.debug('command stdout: %s', out)
    if err:
        LOGGER.debug('command stderr: %s', err)
    return CommandStatus(popen.returncode, out, err)


def run_command(
    command,
    input_data=None,
    out_pipe=subprocess.PIPE,
    err_pipe=subprocess.PIPE,
    env=None,
    **kwargs
):
    """
    Runs a command non-interactively

    Args:
        command(list of str): args of the command to execute, including the
            command itself as command[0] as `['ls', '-l']`
        input_data(str): If passed, will feed that data to the subprocess
            through stdin
        out_pipe(int or file): File descriptor as passed to
            :ref:subprocess.Popen to use as stdout
        err_pipe(int or file): File descriptor as passed to
            :ref:subprocess.Popen to use as stderr
        env(dict of str:str): If set, will use the given dict as env for the
            subprocess
        **kwargs: Any other keyword args passed will be passed to the
            :ref:subprocess.Popen call

    Returns:
        lago.utils.CommandStatus: result of the interactive execution
    """
    if env is None:
        env = os.environ.copy()

    with LogTask(
        'Run command: %s' % ' '.join('"%s"' % arg for arg in command),
        logger=LOGGER,
        level='debug',
    ):
        command_result = _run_command(
            command=command,
            input_data=input_data,
            out_pipe=out_pipe,
            err_pipe=err_pipe,
            env=env,
            **kwargs
        )

        LOGGER.debug('command exit with %d', command_result.code)
        if command_result.out:
            LOGGER.debug('command stdout: %s', command_result.out)
        if command_result.err:
            LOGGER.debug('command stderr: %s', command_result.err)
        return command_result


def run_interactive_command(command, env=None, **kwargs):
    """
    Runs a command interactively, reusing the current stdin, stdout and stderr

    Args:
        command(list of str): args of the command to execute, including the
            command itself as command[0] as `['ls', '-l']`
        env(dict of str:str): If set, will use the given dict as env for the
            subprocess
        **kwargs: Any other keyword args passed will be passed to the
            :ref:subprocess.Popen call

    Returns:
        lago.utils.CommandStatus: result of the interactive execution
    """
    command_result = _run_command(
        command=command,
        out_pipe=sys.stdout,
        err_pipe=sys.stderr,
        stdin=sys.stdin,
        env=env,
        **kwargs
    )
    return command_result


def service_is_enabled(name):
    ret, out, _ = run_command(['systemctl', 'is-enabled', name])
    if ret == 0 and out.strip() == 'enabled':
        return True
    return False


# Copied from VDSM: lib/vdsm/utils.py
class RollbackContext(object):
    '''
    A context manager for recording and playing rollback.
    The first exception will be remembered and re-raised after rollback

    Sample usage:
    > with RollbackContext() as rollback:
    >     step1()
    >     rollback.prependDefer(lambda: undo step1)
    >     def undoStep2(arg): pass
    >     step2()
    >     rollback.prependDefer(undoStep2, arg)

    More examples see tests/utilsTests.py @ vdsm code
    '''

    def __init__(self, *args):
        self._finally = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        """
        If this function doesn't return True (or raises a different
        exception), python re-raises the original exception once this
        function is finished.
        """
        undoExcInfo = None
        for undo, args, kwargs in self._finally:
            try:
                undo(*args, **kwargs)
            except Exception:
                # keep the earliest exception info
                if undoExcInfo is None:
                    undoExcInfo = sys.exc_info()

        if exc_type is None and undoExcInfo is not None:
            raise undoExcInfo[0], undoExcInfo[1], undoExcInfo[2]

    def defer(self, func, *args, **kwargs):
        self._finally.append((func, args, kwargs))

    def prependDefer(self, func, *args, **kwargs):
        self._finally.insert(0, (func, args, kwargs))

    def clear(self):
        self._finally = []


class EggTimer:
    def __init__(self, timeout):
        self.timeout = timeout

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, *_):
        pass

    def elapsed(self):
        return (time.time() - self.start_time) > self.timeout


class ExceptionTimer(object):
    def __init__(self, timeout):
        self.timeout = timeout or 0

    def __enter__(self):
        self.start()

    def __exit__(self, *_):
        self.stop()

    def start(self):
        def raise_timeout(*_):
            raise TimerException('Passed %d seconds' % self.timeout)

        signal.signal(signal.SIGALRM, raise_timeout)
        signal.alarm(self.timeout)

    def stop(self):
        signal.alarm(0)


class LockFile(object):
    """
    Context manager that creates a lock around a directory, with optional
    timeout in the acquire operation

    Args:
        path(str): path to the dir to lock
        timeout(int): timeout in seconds to wait while acquiring the lock
        **kwargs(dict): Any other param to pass to `lockfile.LockFile`
    """

    def __init__(self, path, timeout=None, **kwargs):
        self.path = path
        self.timeout = timeout or 0
        self.lock = lockfile.LockFile(path=path, **kwargs)

    def __enter__(self):
        """
        Start the lock with timeout if needed in the acquire operation

        Raises:
            TimerException: if the timeout is reached before acquiring the lock
        """
        try:
            with ExceptionTimer(timeout=self.timeout):
                with LogTask('Acquiring lock for %s' % self.path):
                    self.lock.acquire()
        except TimerException:
            raise TimerException(
                'Unable to acquire lock for %s in %s secs',
                self.path,
                self.timeout,
            )

    def __exit__(self, *_):
        self.lock.release()


def read_nonblocking(file_descriptor):
    oldfl = fcntl.fcntl(file_descriptor.fileno(), fcntl.F_GETFL)
    try:
        fcntl.fcntl(
            file_descriptor.fileno(),
            fcntl.F_SETFL,
            oldfl | os.O_NONBLOCK,
        )
        return file_descriptor.read()
    finally:
        fcntl.fcntl(file_descriptor.fileno(), fcntl.F_SETFL, oldfl)


def json_dump(obj, f):
    return json.dump(obj, f, indent=4)


def deepcopy(original_obj):
    """
    Creates a deep copy of an object with no crossed referenced lists or dicts,
    useful when loading from yaml as anchors generate those cross-referenced
    dicts and lists

    Args:
        original_obj(object): Object to deep copy

    Return:
        object: deep copy of the object
    """
    if isinstance(original_obj, list):
        return list(deepcopy(item) for item in original_obj)
    elif isinstance(original_obj, dict):
        return dict((key, deepcopy(val)) for key, val in original_obj.items())
    else:
        return original_obj


def load_virt_stream(virt_fd):
    """
    Loads the given conf stream into a dict, trying different formats if
    needed

    Args:
        virt_fd (str): file like objcect with the virt config to load

    Returns:
        dict: Loaded virt config
    """
    try:
        virt_conf = json.load(virt_fd)
    except ValueError:
        virt_fd.seek(0)
        virt_conf = yaml.load(virt_fd)

    return deepcopy(virt_conf)


def in_prefix(prefix_class, workdir_class):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            prefix_path = kwargs.get('prefix_path', None)
            workdir_path = kwargs.get('workdir_path', None)
            if (
                prefix_path is not None or (
                    prefix_class.is_prefix(os.curdir) and workdir_path is None
                )
            ):
                LOGGER.debug('Looking for a prefix')
                prefix_path = os.path.realpath(
                    prefix_class.resolve_prefix_path(prefix_path)
                )
                prefix = prefix_class(prefix_path)
                kwargs['parent_workdir'] = None

            else:
                LOGGER.debug('Looking for a workdir')
                if workdir_path is None:
                    workdir_path = 'auto'

                workdir_path = workdir_class.resolve_workdir_path(workdir_path)
                workdir = workdir_class(path=workdir_path)
                kwargs['parent_workdir'] = workdir
                if kwargs.get('all_envs', False):
                    prefix = workdir
                else:
                    prefix_name = kwargs.get('prefix_name', 'current')
                    prefix = workdir.get_prefix(prefix_name)
                    kwargs['perfix_name'] = prefix_name

                prefix_path = os.path.realpath(
                    os.path.join(workdir_path, prefix_name)
                )

            kwargs['prefix'] = prefix
            os.environ['LAGO_PREFIX_PATH'] = prefix_path or ''
            os.environ['LAGO_WORKDIR_PATH'] = workdir_path or ''
            return func(*args, **kwargs)

        return wrapper

    return decorator


def with_logging(func):
    @functools.wraps(func)
    def wrapper(prefix, *args, **kwargs):
        setup_prefix_logging(prefix.paths.logs())
        return func(*args, prefix=prefix, **kwargs)

    return wrapper


def add_timestamp_suffix(base_string):
    return datetime.datetime.fromtimestamp(
        time.time()
    ).strftime(base_string + '.%Y-%m-%d_%H:%M:%S')


def rotate_dir(base_dir):
    shutil.move(base_dir, add_timestamp_suffix(base_dir))


def ip_to_mac(ip):
    # Mac addrs of domains are 54:52:xx:xx:xx:xx where the last 4 octets are
    # the hex repr of the IP address)
    mac_addr_pieces = [0x54, 0x52] + [int(y) for y in ip.split('.')]
    return ':'.join([('%02x' % x) for x in mac_addr_pieces])
