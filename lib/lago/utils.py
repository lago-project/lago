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
import array
import collections
import fcntl
import functools
import json
import logging
import logging.config
import os
import select
import socket
import subprocess
import sys
import termios
import threading
import time
import tty
import Queue

import config
import constants


def _ret_via_queue(func, queue):
    try:
        queue.put({'return': func()})
    except Exception:
        logging.exception('Error while running thread')
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
            t = threading.Thread(target=_ret_via_queue,
                                 args=(target, q))
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
    'CommandStatus',
    ('code', 'out', 'err')
)


class CommandStatus(_CommandStatus):
    def __nonzero__(self):
        return self.code


def run_command(command, input_data=None, env=None, **kwargs):
    logging.debug('Running command: %s', str(command))

    # add libexec to PATH if needed
    if constants.LIBEXEC_DIR not in os.environ['PATH'].split(':'):
        os.environ['PATH'] = '%s:%s' % (
            constants.LIBEXEC_DIR,
            os.environ['PATH']
        )

    if input_data:
        kwargs['stdin'] = subprocess.PIPE

    if env is None:
        env = os.environ.copy()
    else:
        env['PATH'] = ':'.join(
            list(
                set(
                    env.get('PATH', '').split(':')
                    +
                    os.environ['PATH'].split(':')
                ),
            ),
        )

    popen = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        **kwargs
    )
    out, err = popen.communicate(input_data)
    logging.debug('command exit with %d', popen.returncode)
    if out:
        logging.debug('command stdout: %s', out)
    if err:
        logging.debug('command stderr: %s', err)
    return CommandStatus(popen.returncode, out, err)


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


def setup_logging(logdir):
    if not os.path.exists(logdir):
        os.mkdir(logdir)
    logging.config.fileConfig(
        os.path.join(
            os.path.dirname(__file__),
            'lago.log.conf',
        ),
        defaults={
            'log_path': os.path.join(logdir, 'lago.log'),
            'log_level': config.get('log_level', 'info').upper(),
        },
    )


def _read_nonblocking(f):
    oldfl = fcntl.fcntl(f.fileno(), fcntl.F_GETFL)
    try:
        fcntl.fcntl(f.fileno(), fcntl.F_SETFL, oldfl | os.O_NONBLOCK)
        return f.read()
    finally:
        fcntl.fcntl(f.fileno(), fcntl.F_SETFL, oldfl)


def drain_ssh_channel(chan, stdin=None, stdout=sys.stdout, stderr=sys.stderr):
    chan.settimeout(0)
    out_queue = []
    out_all = []
    err_queue = []
    err_all = []

    try:
        stdout_is_tty = stdout.isatty()
        tty_w = tty_h = -1
    except AttributeError:
        stdout_is_tty = False

    done = False
    while not done:
        if stdout_is_tty:
            arr = array.array('h', range(4))
            if not fcntl.ioctl(stdout.fileno(), termios.TIOCGWINSZ, arr):
                if tty_h != arr[0] or tty_w != arr[1]:
                    tty_h, tty_w = arr[:2]
                    chan.resize_pty(width=tty_w, height=tty_h)

        read_streams = []
        if not chan.closed:
            read_streams.append(chan)

            if stdin and not stdin.closed:
                read_streams.append(stdin)

        write_streams = []
        if stdout and out_queue:
            write_streams.append(stdout)
        if stderr and err_queue:
            write_streams.append(stderr)

        read, write, _ = select.select(
            read_streams,
            write_streams,
            [],
            0.1,
        )

        if stdin in read:
            c = _read_nonblocking(stdin)
            if c:
                chan.send(c)
            else:
                chan.shutdown_write()

        try:
            if chan.recv_ready():
                c = chan.recv(1024)
                if stdout:
                    out_queue.append(c)
                out_all.append(c)

            if chan.recv_stderr_ready():
                c = chan.recv_stderr(1024)
                if stderr:
                    err_queue.append(c)
                err_all.append(c)
        except socket.error:
            pass

        if stdout in write:
            stdout.write(out_queue.pop(0))
            stdout.flush()
        if stderr in write:
            stderr.write(err_queue.pop(0))
            stderr.flush()

        if chan.closed and not out_queue and not err_queue:
            done = True

    return (chan.exit_status, ''.join(out_all), ''.join(err_all))


def interactive_ssh_channel(chan, command=None, stdin=sys.stdin):
    try:
        stdin_is_tty = stdin.isatty()
    except Exception:
        stdin_is_tty = False

    if stdin_is_tty:
        oldtty = termios.tcgetattr(stdin)
        chan.get_pty()

    if command is not None:
        chan.exec_command(command)

    try:
        if stdin_is_tty:
            tty.setraw(stdin.fileno())
            tty.setcbreak(stdin.fileno())
        return CommandStatus(*drain_ssh_channel(chan, stdin))
    finally:
        if stdin_is_tty:
            termios.tcsetattr(stdin, termios.TCSADRAIN, oldtty)


def json_dump(obj, f):
    return json.dump(obj, f, indent=4)
