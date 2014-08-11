import logging
import subprocess
import threading
import Queue


def _ret_via_queue(func, queue):
    try:
        queue.put(func())
    except Exception:
        queue.put(None)


def func_vector(target, argss):
    return map(lambda args: (lambda: target(*args)), argss)


def func_vector_1(target, argss):
    return [(lambda: target(*args)) for args in argss]


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

    def join_all(self):
        if self.results:
            return self.results

        for t, q in self.thread_handles:
            t.join()

        self.results = map(lambda (t, q): q.get(), self.thread_handles)
        return self.results


def run_command(command, **kwargs):
    logging.debug('Running command: %s', str(command))
    popen = subprocess.Popen(command,
                             stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE,
                             **kwargs)
    out, err = popen.communicate()
    logging.debug('command exited with %d', popen.returncode)
    logging.debug('command stdout: %s', out)
    logging.debug('command stderr: %s', err)
    return (popen.returncode, out, err)


def run_ssh_cmd(user, host, cmd):
    return run_command(['ssh', '-q', '-o', 'StrictHostKeyChecking=no',
                        '-o', 'UserKnownHostsFile=/dev/null',
                        '%s@%s' % (user, host), cmd])


def wait_for_ssh(user, host, connect_retries=20):
    while connect_retries:
        ret, _, _ = run_ssh_cmd(user, host, 'true')
        if ret == 0:
            break
        connect_retries -= 1


def scp_to(user, host, local_path, remote_path):
    return run_command(['scp', '-q',
                        '-o', 'StrictHostKeyChecking=no',
                        '-o', 'UserKnownHostsFile=/dev/null',
                        local_path,
                        '%s@%s:%s' % (user, host, remote_path)])


def run_ssh_script(user, host, path, connect_retries=40):
    ret, _, _ = scp_to(user, host, path, '/tmp/runme')
    if ret != 0:
        logging.error('Failed transfering script %s to host %s', path, host)
        raise RuntimeError('Could not transfer script to host')

    logging.debug('Copied script %s to %s', path, host)
    ret, _, _ = run_ssh_cmd(user, host, 'sh /tmp/runme')
    if ret != 0:
        logging.error("Failed to run script %s on '%s'", path, host)
        raise RuntimeError('Script returned with error')

    logging.debug('Script %s finished on %s', path, host)
    ret, _, _ = run_ssh_cmd(user, host, 'rm /tmp/runme')
    if ret != 0:
        logging.error('Failed to remove script %s from host %s',
                      path, host)
        raise RuntimeError('Failed to clean up script')


if __name__ == '__main__':
    test = []

    def foo(n):
        test.append(n)
        if n % 2:
            raise RuntimeError()
        return n
    argss = map(lambda x: (x,), range(10))
    vt = VectorThread(targets=func_vector(foo, argss))
    vt.start_all()
    print vt.join_all()
    print test, len(test)
