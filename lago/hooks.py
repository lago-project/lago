# coding=utf-8

import functools
import lockfile
import logging
import log_utils
import os
from os import path
import shutil
import utils

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)
"""
Hooks
======
Run scripts before or after a Lago command.
The script will be run on the host which runs Lago.
"""


def with_hooks(func):
    """
        Decorate a callable to run with hooks.
        If without hooks==True, don't run the hooks, just the callable.

        Args:
            func(callable): callable to decorate

        Returns:
            The value returned by calling to func

    """

    @functools.wraps(func)
    def wrap(prefix, without_hooks=False, *args, **kwargs):
        kwargs['prefix'] = prefix

        if without_hooks:
            LOGGER.debug('without_hooks=True, skipping hooks')
            return func(*args, **kwargs)

        cmd = func.__name__
        if cmd.startswith('do_'):
            cmd = cmd[3:]

        hooks = Hooks(prefix.paths.hooks())
        hooks.run_pre_hooks(cmd)
        result = func(*args, **kwargs)
        hooks.run_post_hooks(cmd)

        return result

    return wrap


def copy_hooks_to_prefix(config, dir):
    """
        Copy hooks into a prefix.
        All the hooks will be copied to $LAGO_PREFIX_PATH/hooks.
        Symlinks will be created between each hook and the matching
         stage and command
        that were specified in the config.

        For example, the following config:

            "hooks": {
                "start": {
                    "pre": [
                        "$LAGO_INITFILE_PATH/a.py"
                    ],
                    "post": [
                        "$LAGO_INITFILE_PATH/b.sh"
                    ]
                },
                "stop": {
                    "pre": [
                        "$LAGO_INITFILE_PATH/c.sh"
                    ],
                "post": [
                    "$LAGO_INITFILE_PATH/d.sh"
                    ]
                }
            }

        will end up as the following directory structure:

            └── $LAGO_PREFIX_PATH
                ├── hooks
                │   ├── scripts
                │   │   ├── a.py
                │   │   ├── b.sh
                │   │   ├── c.sh
                │   │   └── d.sh
                │   ├── start
                │   │   ├── post
                │   │   │   └── b.sh -> /home/gbenhaim/tmp/fc24/.lago/default
                                                        /hooks/scripts/b.sh
                │   │   └── pre
                │   │       └── a.py -> .lago/default/hooks/scripts/a.py
                │   └── stop
                │       ├── post
                │       │   └── d.sh -> /home/gbenhaim/tmp/fc24/.lago/default
                                                        /hooks/scripts/d.sh
                │       └── pre
                │           └── c.sh -> /home/gbenhaim/tmp/fc24/.lago/default
                                                        /hooks/scripts/c.sh


        Args:
            config(dict): A dict which contains path to hooks categorized by
                command and stage
            dir(str): A path to the ne
        Returns:
            None
    """
    with LogTask('Copying Hooks'):
        scripts_dir = path.join(dir, 'scripts')
        os.mkdir(dir)
        os.mkdir(scripts_dir)

        for cmd, stages in config.viewitems():
            cmd_dir = path.join(dir, cmd)
            os.mkdir(cmd_dir)
            for stage, hooks in stages.viewitems():
                stage_dir = path.join(cmd_dir, stage)
                os.mkdir(stage_dir)
                for idx, hook in enumerate(hooks):
                    hook_src_path = path.expandvars(hook)
                    hook_name = path.basename(hook_src_path)
                    hook_dst_path = path.join(scripts_dir, hook_name)

                    try:
                        shutil.copy(hook_src_path, hook_dst_path)
                        os.symlink(
                            hook_dst_path,
                            path.join(
                                stage_dir, '{}_{}'.format(idx, hook_name)
                            )
                        )
                    except IOError as e:
                        raise utils.LagoUserException(e)


class Hooks(object):

    PRE_CMD = 'pre'
    POST_CMD = 'post'

    def __init__(self, path):
        """
        Args:
            path(list of str): path to the hook dir inside the prefix

        Returns:
            None
        """
        self._path = path

    def run_pre_hooks(self, cmd):
        """
        Run the pre hooks of cmd
        Args:
            cmd(str): Name of the command

        Returns:
            None
        """
        self._run(cmd, Hooks.PRE_CMD)

    def run_post_hooks(self, cmd):
        """
        Run the post hooks of cmd
        Args:
            cmd(str): Name of the command

        Returns:
            None
        """
        self._run(cmd, Hooks.POST_CMD)

    def _run(self, cmd, stage):
        """
        Run the [ pre | post ] hooks of cmd
        Note that the directory of cmd will be locked by this function in
        order to avoid circular call, for example:

        a.sh = lago stop
        b.sh = lago start

        a.sh is post hook of start
        b.sh is post hook of stop

        start -> a.sh -> stop -> b.sh -> start (in this step the hook
        directory of start is locked, so start will be called without
        its hooks)

        Args:
            cmd(str): Name of the command
            stage(str): The stage of the hook

        Returns:
            None
        """
        LOGGER.debug('hook called for {}-{}'.format(stage, cmd))
        cmd_dir = path.join(self._path, cmd)
        hook_dir = path.join(self._path, cmd, stage)

        if not path.isdir(hook_dir):
            LOGGER.debug('{} directory not found'.format(hook_dir))
            return

        _, _, hooks = os.walk(hook_dir).next()

        if not hooks:
            LOGGER.debug('No hooks were found for command: {}'.format(cmd))
            return

        # Avoid Recursion
        try:
            with utils.DirLockWithTimeout(cmd_dir):
                self._run_hooks(
                    sorted([path.join(hook_dir, hook) for hook in hooks])
                )
        except lockfile.AlreadyLocked:
            LOGGER.debug(
                'Hooks dir "{cmd}" is locked, skipping hooks'
                ' for command {cmd}'.format(cmd=cmd)
            )

    def _run_hooks(self, hooks):
        """
        Run a list of scripts.
        Each script should have execute permission.

        Args:
            hooks(list of str): list of path's of the the scrips
                that should be run.

        Returns:
            None

        Raises:
            :exc:HookError: If a script returned code is != 0
        """
        for hook in hooks:
            with LogTask('Running hook: {}'.format(hook)):
                result = utils.run_command([hook])
                if result:
                    raise HookError(
                        'Failed to run hook {}\n{}'.format(hook, result.err)
                    )


class HookError(Exception):
    pass
