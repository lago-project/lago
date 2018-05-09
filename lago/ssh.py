import array
import fcntl
import functools
import select
import socket
import sys
import termios
import time
import tty
import uuid
import logging

import paramiko

from . import (
    utils,
    log_utils,
)
from .config import config

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


def ssh(
    ip_addr,
    command,
    host_name=None,
    data=None,
    show_output=True,
    propagate_fail=True,
    tries=None,
    ssh_key=None,
    username='root',
    password='123456',
):
    host_name = host_name or ip_addr
    client = get_ssh_client(
        ip_addr=ip_addr,
        host_name=host_name,
        propagate_fail=propagate_fail,
        ssh_tries=tries,
        ssh_key=ssh_key,
        username=username,
        password=password,
    )
    transport = client.get_transport()
    channel = transport.open_session()

    joined_command = ' '.join(command)
    command_id = _gen_ssh_command_id()
    LOGGER.debug(
        'Running %s on %s: %s%s',
        command_id,
        host_name,
        joined_command,
        data is not None and (' < "%s"' % data) or '',
    )

    channel.exec_command(joined_command)
    if data is not None:
        channel.send(data)

    channel.shutdown_write()
    return_code, out, err = drain_ssh_channel(
        channel, **(show_output and {} or {
            'stdout': None,
            'stderr': None
        })
    )

    channel.close()
    transport.close()
    client.close()

    LOGGER.debug(
        'Command %s on %s returned with %d',
        command_id,
        host_name,
        return_code,
    )

    if out:
        LOGGER.debug(
            'Command %s on %s output:\n %s',
            command_id,
            host_name,
            out,
        )
    if err:
        LOGGER.debug(
            'Command %s on %s  errors:\n %s',
            command_id,
            host_name,
            err,
        )
    return utils.CommandStatus(return_code, out, err)


def wait_for_ssh(
    ip_addr,
    host_name=None,
    connect_timeout=600,  # 10 minutes
    ssh_key=None,
    username='root',
    password='123456',
):
    host_name = host_name or ip_addr
    start_time = time.time()
    while (time.time() - start_time) < connect_timeout:
        try:
            ret, _, _ = ssh(
                ip_addr=ip_addr,
                host_name=host_name,
                command=['true'],
                tries=1,
                propagate_fail=False,
                ssh_key=ssh_key,
                username=username,
                password=password,
            )
        except Exception as err:
            ret = -1
            sys.exc_clear()
            LOGGER.debug(
                'Got exception while sshing to %s: %s',
                host_name,
                err,
            )

        if ret == 0:
            break

        time.sleep(1)
    else:
        # Try one last time, using the ssh default timeout values, as we
        # already waited for boot_time_sec for sure
        ret, _, _ = ssh(
            ip_addr=ip_addr,
            host_name=host_name,
            command=['true'],
            ssh_key=ssh_key,
            username=username,
            password=password,
        )
        if ret != 0:
            raise RuntimeError(
                'Failed to connect remote shell to %s',
                host_name,
            )

    LOGGER.debug('Wait succeeded for ssh to %s', host_name)


def ssh_script(
    ip_addr,
    path,
    host_name=None,
    show_output=True,
    ssh_key=None,
    username='root',
    password='123456',
):
    host_name = host_name or ip_addr
    LOGGER.debug('Running %s on host %s', path, host_name)
    with open(path) as script_fd:
        return ssh(
            ip_addr=ip_addr,
            host_name=host_name,
            command=['bash', '-s'],
            data=script_fd.read(),
            show_output=show_output,
            ssh_key=ssh_key,
            username=username,
            password=password,
        )


def interactive_ssh(
    ip_addr,
    command=None,
    host_name=None,
    ssh_key=None,
    username='root',
    password='123456',
):
    if command is None:
        command = ['bash']

    client = get_ssh_client(
        ip_addr=ip_addr,
        host_name=host_name,
        ssh_key=ssh_key,
        username=username,
        password=password,
    )
    transport = client.get_transport()
    channel = transport.open_session()
    try:
        return interactive_ssh_channel(channel, ' '.join(command))
    finally:
        channel.close()
        transport.close()
        client.close()


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
            chunk = utils.read_nonblocking(stdin)
            if chunk:
                chan.send(chunk)
            else:
                chan.shutdown_write()

        try:
            if chan.recv_ready():
                chunk = chan.recv(1024)
                if stdout:
                    out_queue.append(chunk)
                out_all.append(chunk)

            if chan.recv_stderr_ready():
                chunk = chan.recv_stderr(1024)
                if stderr:
                    err_queue.append(chunk)
                err_all.append(chunk)
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
        return utils.CommandStatus(*drain_ssh_channel(chan, stdin))
    finally:
        if stdin_is_tty:
            termios.tcsetattr(stdin, termios.TCSADRAIN, oldtty)


def _gen_ssh_command_id():
    return uuid.uuid1().hex[:8]


def get_ssh_client(
    ip_addr,
    ssh_key=None,
    host_name=None,
    ssh_tries=None,
    propagate_fail=True,
    username='root',
    password='123456',
):
    """
    Get a connected SSH client

    Args:
        ip_addr(str): IP address of the endpoint
        ssh_key(str or list of str): Path to a file which
            contains the private key
        hotname(str): The hostname of the endpoint
        ssh_tries(int): The number of attempts to connect to the endpoint
        propagate_fail(bool): If set to true, this event will be in the log
            and fail the outer stage. Otherwise, it will be discarded.
        username(str): The username to authenticate with
        password(str): Used for password authentication
            or for private key decryption

    Raises:
        :exc:`~LagoSSHTimeoutException`: If the client failed to connect after
            "ssh_tries"
    """
    host_name = host_name or ip_addr
    with LogTask(
        'Get ssh client for %s' % host_name,
        level='debug',
        propagate_fail=propagate_fail,
    ):
        ssh_timeout = int(config.get('ssh_timeout'))
        if ssh_tries is None:
            ssh_tries = int(config.get('ssh_tries', 10))

        start_time = time.time()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy(), )
        while ssh_tries > 0:
            try:
                client.connect(
                    ip_addr,
                    username=username,
                    password=password,
                    key_filename=ssh_key,
                    timeout=ssh_timeout,
                )
                break
            except (socket.error, socket.timeout) as err:
                LOGGER.debug(
                    'Socket error connecting to %s: %s',
                    host_name,
                    err,
                )
            except paramiko.ssh_exception.SSHException as err:
                LOGGER.debug(
                    'SSH error connecting to %s: %s',
                    host_name,
                    err,
                )
            except EOFError as err:
                LOGGER.debug('EOFError connecting to %s: %s', host_name, err)
            ssh_tries -= 1
            LOGGER.debug(
                'Still got %d tries for %s',
                ssh_tries,
                host_name,
            )
            time.sleep(1)
        else:
            end_time = time.time()
            raise LagoSSHTimeoutException(
                'Timed out (in %d s) trying to ssh to %s' %
                (end_time - start_time, host_name)
            )

    return client


class LagoSSHTimeoutException(utils.LagoException):
    pass
