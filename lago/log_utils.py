#
# Copyright 2015-2017 Red Hat, Inc.
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
"""
This module defines the special logging tools that lago uses
"""
from future.builtins import super
import logging
import logging.config
import os
import re
import traceback
import datetime
import threading
import uuid as uuid_m
from collections import (
    OrderedDict,
    deque,
)
from functools import wraps

#: Message to be shown when a task is started
START_TASK_MSG = ''
#: Message template that will trigger a task
START_TASK_TRIGGER_MSG = 'start task%s'
#: Regexp that will match the above template
START_TASK_REG = re.compile('start task(?P<task_name>.*)')
#: Message to be shown when a task is ended
END_TASK_MSG = 'Success'
END_TASK_ON_ERROR_MSG = 'ERROR'
#: Message template that will trigger a task end
END_TASK_TRIGGER_MSG = 'end task%s'
#: Regexp that will match the above template
END_TASK_REG = re.compile('end task(?P<task_name>.*)')
#: Message template that will always shoud the messago
ALWAYS_SHOW_TRIGGER_MSG = 'force-show:%s'
#: Regexp that will match the above template
ALWAYS_SHOW_REG = re.compile('force-show:(?P<message>.*)')


class ColorFormatter(logging.Formatter):
    """
    Formatter to add colors to log records
    """
    DEFAULT = '\x1b[0m'
    RED = '\x1b[31m'
    GREEN = '\x1b[32m'
    YELLOW = '\x1b[33m'
    CYAN = '\x1b[36m'
    WHITE = '\x1b[37m'
    NONE = ''
    CRITICAL = RED
    ERROR = RED
    WARNING = YELLOW
    INFO = CYAN
    DEBUG = NONE

    @classmethod
    def colored(cls, color, message):
        """
        Small function to wrap a string around a color

        Args:
            color (str): name of the color to wrap the string with, must be one
                of the class properties
            message (str): String to wrap with the color

        Returns:
            str: the colored string
        """
        return getattr(cls, color.upper()) + message + cls.DEFAULT

    def format(self, record):
        """
        Adds colors to a log record and formats it with the default

        Args:
            record (logging.LogRecord): log record to format

        Returns:
            str: The colored and formatted record string
        """
        level = record.levelno

        if level >= logging.CRITICAL:
            color = self.CRITICAL
        elif level >= logging.ERROR:
            color = self.ERROR
        elif level >= logging.WARNING:
            color = self.WARNING
        elif level >= logging.INFO:
            color = self.INFO
        elif level >= logging.DEBUG:
            color = self.DEBUG
        else:
            color = self.DEFAULT

        message = super().format(record)
        if record.args:
            try:
                message = message % record.args
            except TypeError:
                # this happens when the message itself has some %s symbols, as
                # in traces for tracedumps
                pass

        return color + message + self.DEFAULT


class Task(deque):
    """
    Small wrapper around deque to add the failed status and name to a task

    Attributes:
        name (str): name for this task
        failed (bool): If this task has failed or not (if there was any error
            log shown during it's execution)
        force_show (bool): If set, will show any log records generated inside
            this task even if it's out of nested depth limit
    """

    def __init__(self, name, *args, **kwargs):
        """
        Args:
            name (str): name for this task
            *args: any :class:`deque` args
            *kwargs: any :class:`deque` kwargs
        """
        self.failed = False
        self.force_show = False
        self.name = name
        self.start_time = datetime.datetime.now()
        super(Task, self).__init__(*args, **kwargs)

    def __str__(self):
        return (
            '%s(failed=%s, force_show=%s, len=%d)' %
            (self.name, self.failed, self.force_show, len(self))
        )

    def elapsed_time(self):
        return str(datetime.datetime.now() - self.start_time).rsplit('.', 1)[0]


class ContextLock(object):
    """
    Context manager to thread lock a block of code
    """

    def __init__(self):
        self.lock = threading.Lock()

    def __enter__(self):
        self.lock.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.lock.release()


class TaskHandler(logging.StreamHandler):
    """
    This log handler will use the concept of tasks, to hide logs, and will show
    all the logs for the current task if there's a logged error while running
    that task.

    It will hide any logs that belong to nested tasks that have more than
    ``task_tree_depth`` parent levels, and for the ones that are above that
    level, it will show only the logs that have a loglevel above
    ``level``.

    You can force showing a log record immediately if you use the
    :func:`log_always` function bypassing all the filters.

    If there's a log record with log level higher than ``dump_level`` it will
    be considered a failure, and all the logs for the current task that have a
    log level above ``level`` will be shown no matter at which depth the task
    belongs to. Also, all the parent tasks will be tagged as error.

    Attributes:
        formatter (logging.LogFormatter): formatter to use
        initial_depth (int): Initial depth to account for, in case this handler
            was created in a subtask
        tasks_by_thread (dict of str: OrderedDict of str: Task): List of
            thread names, and their currently open tasks with  their latest
            log records
        dump_level (int): log level from which to consider a log record as
            error
        buffer_size (int): Size of the log record deque for each task, the
            bigger, the more records it can show in case of error but the more
            memory it will use
        task_tree_depth (int): number of the nested level to show start/end
            task logs for, if -1 will show always
        level (int): Log level to show logs from if the depth limit is not
            reached
        main_failed (bool): used to flag from a child thread that the main
            should fail any current task
        _tasks_lock (ContextLock): Lock for the tasks_by_thread dict
        _main_thread_lock (ContextLock): Lock for the main_failed bool
    """
    #: List of chars to show as task prefix, to ease distinguishing them
    TASK_INDICATORS = ['@', '#', '*', '-', '~']

    def __init__(
        self,
        initial_depth=0,
        task_tree_depth=-1,
        buffer_size=2000,
        dump_level=logging.ERROR,
        level=logging.NOTSET,
        formatter=ColorFormatter,
    ):
        super().__init__()
        self.formatter = formatter
        self.initial_depth = initial_depth
        self.tasks_by_thread = {}
        self.dump_level = dump_level
        self.buffer_size = buffer_size
        self.task_tree_depth = task_tree_depth
        self.level = level
        self.main_failed = False
        self._tasks_lock = ContextLock()
        self._main_thread_lock = ContextLock()

    @property
    def cur_task(self):
        """
        Returns:
            str: the current active task
        """
        return self.tasks.keys()[-1] if self.tasks else None

    @property
    def cur_thread(self):
        """
        Returns:
            str: Name of the current thread
        """
        return threading.current_thread().name

    @property
    def tasks(self):
        """
        Returns:
            OrderedDict of str, Task: list of task names and log records for
                each for the current thread
        """
        return self.get_tasks(thread_name=self.cur_thread)

    def get_tasks(self, thread_name):
        """
        Args:
            thread_name (str): name of the thread to get the tasks for

        Returns:
            OrderedDict of str, Task: list of task names and log records for
                each for the given thread
        """
        if thread_name not in self.tasks_by_thread:
            with self._tasks_lock:
                self.tasks_by_thread[thread_name] = OrderedDict()

        return self.tasks_by_thread[thread_name]

    @property
    def cur_depth_level(self):
        """
        Returns:
            int: depth level for the current task
        """
        cur_level = self.initial_depth
        if not self.am_i_main_thread:
            cur_level += len(self.get_tasks(thread_name='MainThread'))

        return cur_level + len(self.tasks)

    @property
    def am_i_main_thread(self):
        """
        Returns:
            bool: if the current thread is the main thread
        """
        return threading.current_thread().name == 'MainThread'

    def mark_main_tasks_as_failed(self):
        """
        Flags to the main thread that all it's tasks sholud fail

        Returns:
            None
        """
        if self.am_i_main_thread:
            return

        with self._main_thread_lock:
            self.main_failed = True

    def should_show_by_depth(self, cur_level=None):
        """
        Args:
            cur_level (int): depth level to take into account

        Returns:
            bool: True if the given depth level should show messages (not
                taking into account the log level)
        """
        if cur_level is None:
            cur_level = self.cur_depth_level

        return (self.task_tree_depth < 0 or self.task_tree_depth >= cur_level)

    def should_show_by_level(self, record, base_level=None):
        """
        Args:
            record_level (int): log level of the record to check
            base_level (int or None): log level to check against, will use the
                object's :class:`dump_level` if None is passed

        Returns:
            bool: True if the given log record should be shown according to the
                log level
        """
        if base_level is None:
            base_level = self.dump_level

        return record.levelno >= base_level

    def handle_new_task(self, task_name, record):
        """
        Do everything needed when a task is starting

        Params:
            task_name (str): name of the task that is starting
            record (logging.LogRecord): log record with all the info

        Returns:
            None
        """
        record.msg = ColorFormatter.colored('default', START_TASK_MSG)
        record.task = task_name

        self.tasks[task_name] = Task(name=task_name, maxlen=self.buffer_size)
        if self.should_show_by_depth():
            self.pretty_emit(record, is_header=True)

    def mark_parent_tasks_as_failed(self, task_name, flush_logs=False):
        """
        Marks all the parent tasks as failed

        Args:
            task_name (str): Name of the child task
            flush_logs (bool): If ``True`` will discard all the logs form
                parent tasks

        Returns:
            None
        """
        for existing_task_name in self.tasks:
            if existing_task_name == task_name:
                break

            if flush_logs:
                self.tasks[existing_task_name].clear()

            self.tasks[existing_task_name].failed = True

        self.mark_main_tasks_as_failed()

    def close_children_tasks(self, parent_task_name):
        """
        Closes all the children tasks that were open

        Args:
            parent_task_name (str): Name of the parent task

        Returns:
            None
        """
        if parent_task_name not in self.tasks:
            return

        while self.tasks:
            next_task = reversed(self.tasks.keys()).next()
            if next_task == parent_task_name:
                break
            del self.tasks[next_task]

    def handle_closed_task(self, task_name, record):
        """
        Do everything needed when a task is closed

        Params:
            task_name (str): name of the task that is finishing
            record (logging.LogRecord): log record with all the info

        Returns:
            None
        """
        if task_name not in self.tasks:
            return

        if self.main_failed:
            self.mark_parent_tasks_as_failed(self.cur_task)

        if self.tasks[task_name].failed:
            record.msg = ColorFormatter.colored('red', END_TASK_ON_ERROR_MSG)
        else:
            record.msg = ColorFormatter.colored('green', END_TASK_MSG)

        record.msg += ' (in %s)' % self.tasks[task_name].elapsed_time()

        if self.should_show_by_depth() or self.tasks[task_name].force_show:
            if self.tasks[task_name].force_show:
                self.handle_error()

            self.pretty_emit(record, is_header=True)

        self.close_children_tasks(task_name)
        self.tasks.pop(task_name)

    def handle_error(self):
        """
        Handles an error log record that should be shown

        Returns:
            None
        """
        if not self.tasks:
            return

        # All the parents inherit the failure
        self.mark_parent_tasks_as_failed(
            self.cur_task,
            flush_logs=True,
        )

        # Show the start headers for all the parent tasks if they were not
        # shown by the depth level limit
        for index, task in enumerate(self.tasks.values()):
            if self.should_show_by_depth(index + 1):
                continue

            start_task_header = logging.LogRecord(
                '', logging.INFO, '', 0, '', [], None
            )
            start_task_header.msg = ColorFormatter.colored(
                'default',
                START_TASK_MSG,
            )
            start_task_header.task = task.name
            self.pretty_emit(
                start_task_header,
                is_header=True,
                task_level=index + 1,
            )

        # Show now all the cached logs for the current task
        for old_record in self.tasks[self.cur_task]:
            self.pretty_emit(old_record)

        self.tasks[self.cur_task].clear()

    def get_task_indicator(self, task_level=None):
        """
        Args:
            task_level (int or None): task depth level to get the indicator
                for, if None, will use the current tasks depth

        Returns:
            str: char to prepend to the task logs to indicate it's level
        """
        if task_level is None:
            task_level = len(self.tasks)
        return self.TASK_INDICATORS[task_level % len(self.TASK_INDICATORS)]

    def pretty_emit(self, record, is_header=False, task_level=None):
        """
        Wrapper around the :class:`logging.StreamHandler` emit method to add
        some decoration stuff to the message

        Args:
            record (logging.LogRecord): log record to emit
            is_header (bool): if this record is a header, usually, a start or
                end task message
            task_level (int): If passed, will take that as the current nested
                task level instead of calculating it from the current tasks

        Returns:
            None
        """
        task = record.task or self.cur_task
        if task_level is None:
            task_level = self.cur_depth_level

        if is_header:
            extra_prefix = (
                self.get_task_indicator(task_level - 1) + ' ' +
                ('' if self.am_i_main_thread else '[%s] ' % self.cur_thread) +
                task + ': '
            )
            record.levelno = logging.INFO
        else:
            extra_prefix = '  ' + self.get_task_indicator(task_level) + ' '

        if task:
            record.msg = (
                '  ' * (task_level - 1) + extra_prefix + str(record.msg)
            )

        super().emit(record)
        super().flush()

    def emit(self, record):
        """
        Handle the given record, this is the entry point from the python
        logging facility

        Params:
            record (logging.LogRecord): log record to handle

        Returns:
            None
        """
        record.task = self.cur_task

        if record.levelno >= self.dump_level and self.cur_task:
            self.tasks[self.cur_task].failed = True
            self.tasks[self.cur_task].force_show = True

        # Makes no sense to start a task with an error log
        is_start = START_TASK_REG.match(str(record.msg))
        if is_start:
            self.handle_new_task(is_start.groupdict()['task_name'], record)
            return

        is_end = END_TASK_REG.match(str(record.msg))
        if is_end:
            self.handle_closed_task(is_end.groupdict()['task_name'], record)
            return

        force_show_record = ALWAYS_SHOW_REG.match(str(record.msg))
        if force_show_record:
            record.msg = force_show_record.groupdict()['message']
            self.pretty_emit(record)

        if (
            not force_show_record and self.should_show_by_level(record)
            and self.should_show_by_depth()
        ):
            self.pretty_emit(record)
            return

        if self.cur_task:
            self.tasks[self.cur_task].append(record)


class LogTask(object):
    """
    Context manager for a log task

    Example:
        >>> with LogTask('mytask'):
        ...     pass
    """

    def __init__(
        self,
        task,
        logger=logging,
        level='info',
        propagate_fail=True,
        uuid=None,
    ):
        self.task = task
        self.logger = logger
        self.level = level
        self.propagate = propagate_fail
        if uuid is None:
            self.uuid = uuid_m.uuid4()
        self.header = self.task
        if self.level != 'info':
            self.header = ':{0}:{1}:'.format(str(self.uuid), self.task)

    def __enter__(self):
        getattr(self.logger, self.level)(START_TASK_TRIGGER_MSG % self.header)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type and self.propagate:
            end_log_task(self.header, level='error')
            str_tb = ''.join(traceback.format_tb(exc_tb))
            self.logger.debug(str_tb)
            return False
        else:
            getattr(self.logger,
                    self.level)(END_TASK_TRIGGER_MSG % self.header)


def log_task(
    task, logger=logging, level='info', propagate_fail=True, uuid=None
):
    """
    Parameterized decorator to wrap a function in a log task

    Example:
        >>> @log_task('mytask')
        ... def do_something():
        ...     pass
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            with LogTask(
                task,
                logger=logger,
                level=level,
                propagate_fail=propagate_fail,
                uuid=uuid
            ):
                return func(*args, **kwargs)

        return wrapper

    return decorator


def start_log_task(task, logger=logging, level='info'):
    """
    Starts a log task

    Args:
        task (str): name of the log task to start
        logger (logging.Logger): logger to use
        level (str): log level to use

    Returns:
        None
    """
    getattr(logger, level)(START_TASK_TRIGGER_MSG % task)


def end_log_task(task, logger=logging, level='info'):
    """
    Ends a log task

    Args:
        task (str): name of the log task to end
        logger (logging.Logger): logger to use
        level (str): log level to use

    Returns:
        None
    """
    getattr(logger, level)(END_TASK_TRIGGER_MSG % task)


def log_always(message):
    """
    Wraps the given message with a tag that will make it be always logged by
    the task logger

    Args:
        message (str): message to wrap with the tag

    Returns:
        str: tagged message that will get it shown immediately by the task
            logger
    """
    return ALWAYS_SHOW_TRIGGER_MSG % message


def hide_paramiko_logs():
    paramiko_logger = logging.getLogger('paramiko.transport')
    paramiko_logger.propagate = False
    paramiko_logger.setLevel(logging.ERROR)


def hide_stevedore_logs():
    """
    Hides the logs of stevedore, this function was
    added in order to support older versions of stevedore

    We are using the NullHandler in order to get rid from
    'No handlers could be found for logger...' msg

    Returns:
        None
    """
    stevedore_logger = logging.getLogger('stevedore.extension')
    stevedore_logger.propagate = False
    stevedore_logger.setLevel(logging.ERROR)
    stevedore_logger.addHandler(logging.NullHandler())


def setup_prefix_logging(logdir):
    """
    Sets up a file logger that will create a log in the given logdir (usually a
    lago prefix)

    Args:
        logdir (str): path to create the log into, will be created if it does
            not exist

    Returns:
        None
    """
    if not os.path.exists(logdir):
        os.mkdir(logdir)

    file_handler = logging.FileHandler(
        filename=os.path.join(logdir, 'lago.log'),
    )
    file_formatter = get_default_log_formatter()
    file_handler.setFormatter(file_formatter)
    logging.root.addHandler(file_handler)
    hide_paramiko_logs()
    hide_stevedore_logs()


def get_default_log_formatter():
    return logging.Formatter(
        fmt=(
            '%(asctime)s::%(filename)s::%(funcName)s::%(lineno)s::'
            '%(name)s::%(levelname)s::%(message)s'
        ),
    )
