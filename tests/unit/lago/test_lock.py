import signal
from multiprocessing import Process, Event
from os import WNOHANG, kill, waitpid
from time import sleep

import pytest

from lago.utils import LockFile, TimerException


def lock_path(run_path, duration, event=None):
    with LockFile(run_path):
        if event:
            event.set()
        sleep(duration)


class ProcessWrapper(object):
    def __init__(self, daemon=True, **kwargs):
        self._p = Process(**kwargs)
        self._p.daemon = daemon

    def __getattr__(self, name):
        return getattr(self._p, name)

    def kill(self, sig=None):
        sig = signal.SIGKILL if sig is None else sig
        kill(self.pid, sig)

    def waitpid(self):
        return waitpid(self.pid, WNOHANG)

    def __enter__(self):
        self.start()

    def __exit__(self, *args):
        self.kill()


@pytest.fixture
def lockfile(tmpdir):
    return str(tmpdir.join('test-lock'))


@pytest.fixture
def event():
    return Event()


@pytest.fixture
def p_wrapper(lockfile, event):
    duration = 60
    event.clear()

    return ProcessWrapper(target=lock_path, args=(lockfile, duration, event))


def test_should_fail_to_lock_when_already_locked(lockfile, p_wrapper, event):
    with p_wrapper:
        assert event.wait(30), 'Timeout while waiting for child process'
        with pytest.raises(TimerException), LockFile(lockfile, timeout=1):
            pass


def test_should_succeed_to_lock_a_stale_lock(lockfile, p_wrapper, event):
    p_wrapper.start()
    assert event.wait(30), 'Timeout while waiting for child process'

    p_wrapper.kill()
    # If the process is still running waitpid returns (0, 0)
    assert not any(p_wrapper.waitpid()), 'Failed to kill child process'

    with LockFile(lockfile, timeout=1):
        pass
