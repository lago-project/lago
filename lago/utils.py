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
import tempfile
import textwrap
import time
import yaml
import pkg_resources
from io import StringIO
import argparse
import configparser
import uuid as uuid_m
from . import constants
from .log_utils import (LogTask, setup_prefix_logging)
import hashlib

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
        LOGGER.debug(
            'Error while running thread %s',
            threading.current_thread().name,
            exc_info=True
        )
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
    return vt.join_all()


def invoke_different_funcs_in_parallel(*funcs):
    vt = VectorThread(funcs)
    vt.start_all()
    return vt.join_all()


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
    uuid=None,
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
        uuid(uuid): If set the command will be logged with the given uuid
            converted to string, otherwise, a uuid v4 will be generated.
        **kwargs: Any other keyword args passed will be passed to the
            :ref:subprocess.Popen call

    Returns:
        lago.utils.CommandStatus: result of the interactive execution
    """

    # add libexec to PATH if needed
    if uuid is None:
        uuid = uuid_m.uuid4()

    if constants.LIBEXEC_DIR not in os.environ['PATH'].split(':'):
        os.environ['PATH'
                   ] = '%s:%s' % (constants.LIBEXEC_DIR, os.environ['PATH'])

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
                    env.get('PATH', '').split(':') + os.environ['PATH']
                    .split(':')
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
    LOGGER.debug(
        '%s: command exit with return code: %d', str(uuid), popen.returncode
    )
    if out:
        LOGGER.debug('%s: command stdout: %s', str(uuid), out)
    if err:
        LOGGER.debug('%s: command stderr: %s', str(uuid), err)
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
    ) as task:
        command_result = _run_command(
            command=command,
            input_data=input_data,
            out_pipe=out_pipe,
            err_pipe=err_pipe,
            env=env,
            uuid=task.uuid,
            **kwargs
        )
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


class Flock(object):
    """A wrapper class around flock

    Attributes:
        path(str): Path to the lock file
        readonly(bool): If true create a shared lock, otherwise
            create an exclusive lock.
        blocking(bool) If true block the calling process if the
            lock is already acquired.
    """

    def __init__(self, path, readonly=False, blocking=True):
        self._path = path
        self._fd = None
        if readonly:
            self._op = fcntl.LOCK_SH
        else:
            self._op = fcntl.LOCK_EX

        if not blocking:
            self._op |= fcntl.LOCK_NB

    def acquire(self):
        """Acquire the lock

        Raises:
            IOError: if the call to flock fails
        """
        self._fd = open(self._path, mode='w+')
        os.chmod(self._path, 0o660)
        fcntl.flock(self._fd, self._op)

    def release(self):
        self._fd.close()


class LockFile(object):
    """
    Context manager that creates a file based lock, with optional
    timeout in the acquire operation.

    This context manager should be used only from the main Thread.

    Args:
        path(str): path to the dir to lock
        timeout(int): timeout in seconds to wait while acquiring the lock
        lock_cls(callable): A callable which returns a Lock object that
            implements the acquire and release methods.
            The default is Flock.
        **kwargs(dict): Any other param to pass to the `lock_cls` instance.

    """

    def __init__(self, path, timeout=None, lock_cls=None, **kwargs):
        self.path = path
        self.timeout = timeout or 0
        self._lock_cls = lock_cls or Flock
        self.lock = self._lock_cls(path=path, **kwargs)

    def __enter__(self):
        """
        Start the lock with timeout if needed in the acquire operation

        Raises:
            TimerException: if the timeout is reached before acquiring the lock
        """
        try:
            with ExceptionTimer(timeout=self.timeout):
                LOGGER.debug('Acquiring lock for {}'.format(self.path))
                self.lock.acquire()
                LOGGER.debug('Holding the lock for {}'.format(self.path))
        except TimerException:
            raise TimerException(
                'Unable to acquire lock for %s in %s secs',
                self.path,
                self.timeout,
            )

    def __exit__(self, *_):
        LOGGER.debug('Trying to release lock for {}'.format(self.path))
        self.lock.release()
        LOGGER.debug('Lock for {} was released'.format(self.path))


class TemporaryDirectory(object):
    """
    Context manager that creates a temporary directory and provides
    its path as a property.

    Args:
        ignore_errors(bool): ignore errors when trying to remove directory
    Raises:
        OSError: anything that 'shutil.rmtree' might raise
    """

    def __init__(self, ignore_errors=True):
        self._path = tempfile.mkdtemp()
        self._ignore_errors = ignore_errors

    def __enter__(self):
        return self._path

    def __exit__(self, *_):
        shutil.rmtree(self._path, self._ignore_errors)


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
                    kwargs['prefix_name'] = prefix_name

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


def ipv4_to_mac(ip):
    # Mac addrs of domains are 54:52:xx:xx:xx:xx where the last 4 octets are
    # the hex repr of the IP address)
    mac_addr_pieces = [0x54, 0x52] + [int(y) for y in ip.split('.')]
    return ':'.join([('%02x' % x) for x in mac_addr_pieces])


def argparse_to_ini(parser, root_section='lago', incl_unset=False):
    subparsers_actions = [
        action for action in parser._actions
        if isinstance(action, argparse._SubParsersAction)
    ]

    root_actions = [
        action for action in parser._actions
        if not isinstance(action, argparse._SubParsersAction)
    ]

    cp = configparser.ConfigParser(allow_no_value=True)

    _add_subparser_to_cp(cp, root_section, root_actions, incl_unset)
    for subparsers_action in subparsers_actions:
        for choice, subparser in subparsers_action.choices.items():
            _add_subparser_to_cp(cp, choice, subparser._actions, incl_unset)

    header = '# Lago configuration file, generated: {0}'.format(
        time.strftime("%c")
    )
    with StringIO() as ini_str:
        cp.write(ini_str)
        return '\n'.join([header, ini_str.getvalue()])


def _add_subparser_to_cp(cp, section, actions, incl_unset):
    cp.add_section(section)
    print_actions = (
        action for action in actions
        if (action.default and action.default != '==SUPPRESS==') or
        (action.default is None and incl_unset)
    )
    for action in print_actions:
        var = str(action.dest)
        if action.default is None:
            var = '#{0}'.format(var)
        if action.help:
            for line in textwrap.wrap(action.help, width=70):
                cp.set(section, '# {0}'.format(line))
        cp.set(section, var, str(action.default))
    if len(cp.items(section)) == 0:
        cp.remove_section(section)


def run_command_with_validation(
    cmd, fail_on_error=True, msg='An error has occurred'
):
    result = run_command(cmd)
    if result and fail_on_error:
        raise RuntimeError('{}\n{}'.format(msg, result.err))

    return result


def get_qemu_info(path, backing_chain=False, fail_on_error=True):
    """
    Get info on a given qemu disk

    Args:
        path(str): Path to the required disk
        backing_chain(boo): if true, include also info about
        the image predecessors.
    Return:
        object: if backing_chain == True then a list of dicts else a dict
    """

    cmd = ['qemu-img', 'info', '--output=json', path]

    if backing_chain:
        cmd.insert(-1, '--backing-chain')

    result = run_command_with_validation(
        cmd, fail_on_error, msg='Failed to get info for {}'.format(path)
    )

    return json.loads(result.out)


def qemu_rebase(target, backing_file, safe=True, fail_on_error=True):
    """
    changes the backing file of 'source' to 'backing_file'
    If backing_file is specified as "" (the empty string),
    then the image is rebased onto no backing file
    (i.e. it will exist independently of any backing file).
    (Taken from qemu-img man page)

    Args:
        target(str): Path to the source disk
        backing_file(str): path to the base disk
        safe(bool): if false, allow unsafe rebase
         (check qemu-img docs for more info)
    """
    cmd = ['qemu-img', 'rebase', '-b', backing_file, target]
    if not safe:
        cmd.insert(2, '-u')

    return run_command_with_validation(
        cmd,
        fail_on_error,
        msg='Failed to rebase {target} onto {backing_file}'.format(
            target=target, backing_file=backing_file
        )
    )


def compress(input_file, block_size, fail_on_error=True):
    cmd = [
        'xz', '--compress', '--keep', '--threads=0', '--best', '--force',
        '--verbose', '--block-size={}'.format(block_size), input_file
    ]
    return run_command_with_validation(
        cmd, fail_on_error, msg='Failed to compress {}'.format(input_file)
    )


def cp(input_file, output_file, fail_on_error=True):
    if not os.path.basename(output_file):
        output_file = os.path.join(output_file, os.path.basename(input_file))

    cmd = ['cp', input_file, output_file]
    return run_command_with_validation(
        cmd,
        fail_on_error,
        msg='Failed to copy {} to {}'.format(input_file, output_file)
    )


def sparse(input_file, input_format, fail_on_error=True):
    cmd = [
        'virt-sparsify',
        '-q',
        '-v',
        '--format',
        input_format,
        '--in-place',
        input_file,
    ]
    return run_command_with_validation(
        cmd, fail_on_error, msg='Failed to sparse {}'.format(input_file)
    )


def get_hash(file_path, checksum='sha1'):
    """
    Generate a hash for the given file

    Args:
        file_path (str): Path to the file to generate the hash for
        checksum (str): hash to apply, one of the supported by hashlib, for
            example sha1 or sha512

    Returns:
        str: hash for that file
    """

    sha = getattr(hashlib, checksum)()
    with open(file_path) as file_descriptor:
        while True:
            chunk = file_descriptor.read(65536)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def filter_spec(spec, paths, wildcard='*', separator='/'):
    """
    Remove keys from a spec file.
    For example, with the following path: domains/*/disks/*/metadata
    all the metadata dicts from all domains disks will be removed.

    Args:
        spec (dict): spec to remove keys from
        paths (list): list of paths to the keys that should be removed
        wildcard (str): wildcard character
        separator (str): path separator

    Returns:
        None

    Raises:
        utils.LagoUserException: If a malformed path was detected
    """

    def remove_key(path, spec):
        if len(path) == 0:
            return
        elif len(path) == 1:
            key = path.pop()
            if not isinstance(spec, collections.Mapping):
                raise LagoUserException(
                    'You have tried to remove the following key - "{key}".\n'
                    'Keys can not be removed from type {spec_type}\n'
                    'Please verify that path - "{{path}}" is valid'.format(
                        key=key, spec_type=type(spec)
                    )
                )
            if key == wildcard:
                spec.clear()
            else:
                spec.pop(key, None)
        else:
            current = path[0]
            if current == wildcard:
                if isinstance(spec, list):
                    iterator = iter(spec)
                elif isinstance(spec, collections.Mapping):
                    iterator = spec.itervalues()
                else:
                    raise LagoUserException(
                        'Glob char {char} should refer only to dict or list, '
                        'not to {spec_type}\n'
                        'Please fix path - "{{path}}"'.format(
                            char=wildcard, spec_type=type(spec)
                        )
                    )

                for i in iterator:
                    remove_key(path[1:], i)
            else:
                try:
                    remove_key(path[1:], spec[current])
                except KeyError:
                    raise LagoUserException(
                        'Malformed path "{{path}}", key "{key}" '
                        'does not exist'.format(key=current)
                    )
                except TypeError:
                    raise LagoUserException(
                        'Malformed path "{{path}}", can not get '
                        'by key from type {spec_type}'.format(
                            spec_type=type(spec)
                        )
                    )

    for path in paths:
        try:
            remove_key(path.split(separator), spec)
        except LagoUserException as e:
            e.message = e.message.format(path=path)
            raise


def ver_cmp(ver1, ver2):
    """
    Compare lago versions

    Args:
        ver1(str): version string
        ver2(str): version string

    Returns:
        Return negative if ver1<ver2, zero if ver1==ver2, positive if
        ver1>ver2.
    """

    return cmp(
        pkg_resources.parse_version(ver1), pkg_resources.parse_version(ver2)
    )


class LagoException(Exception):
    pass


class LagoInitException(LagoException):
    pass


class LagoUserException(LagoException):
    pass
