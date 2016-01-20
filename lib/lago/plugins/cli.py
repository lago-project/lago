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
"""
About CLIPlugins

A CLIPlugin is a subcommand of the lagocli command, it's ment to group
actions together in a logical sense, for example grouping all the actions
done to templates.

To create a new subcommand for testenvcli you just have to subclass the
CLIPlugin abstract class and declare it in the setuptools as an entry_point,
see this module's setup.py/setup.cfg for an example::

    class NoopCLIplugin(CLIPlugin):
        help = 'dummy help string'

        def populate_parser(self, parser):
            parser.addArgument('--dummy-flag', action='store_true')

        def do_run(self, args):
            if args.dummy_flag:
                print "Dummy flag passed to noop subcommand!"
            else:
                print "Dummy flag not passed to noop subcommand!"


You can also use decorators instead, an equivalent is::

    @cli_plugin_add_argument('--dummy-flag', action='store_true')
    @cli_plugin_add_help('dummy help string')
    def my_fancy_plugin_func(dummy_flag, **kwargs):
        if dummy_flag:
            print "Dummy flag passed to noop subcommand!"
        else:
            print "Dummy flag not passed to noop subcommand!"

Or::

    @cli_plugin_add_argument('--dummy-flag', action='store_true')
    def my_fancy_plugin_func(dummy_flag, **kwargs):
        "dummy help string"
        if dummy_flag:
            print "Dummy flag passed to noop subcommand!"
        else:
            print "Dummy flag not passed to noop subcommand!"


Then you will need to add an entry_points section in your setup.py like::

    setup(
        ...
        entry_points={
            'lago.plugins.cli': [
                'noop=noop_module:my_fancy_plugin_func',
            ],
        }
        ...
    )


Or in your setup.cfg like::

    [entry_points]
    lago.plugins.cli =
        noop=noop_module:my_fancy_plugin_func



Any of those will add a new subcommand to the lagocli command that can be run
as::

    $ lagocli noop
    Dummy flag not passed to noop subcommand!

TODO: Allow per-plugin namespacing to get rid of the `**kwargs` parameter
"""

from abc import (
    abstractmethod,
    abstractproperty,
    ABCMeta,
)


class CLIPlugin(object):
    __metaclass__ = ABCMeta

    def __init__(self):
        pass

    @abstractproperty
    def help(self):
        """
        Help string for the subcommand (as shown in the command line help)
        """

    @abstractmethod
    def populate_parser(self, parser):
        """
        Add any required arguments to the parser

        Args:
            parser (ArgumentParser): parser to add the arguments to

        Returns:
            None
        """

    @abstractmethod
    def do_run(self, args):
        """
        Execute any actions given the arguments

        Args:
            args (Namespace): with the arguments

        Returns:
            None
        """


class CLIPluginFuncWrapper(CLIPlugin):
    """
    Special class to handle decorated cli plugins, take into account that the
    decorated functions have some limitations on what arguments can they
    define actually, if you need something complicated, used the abstract class
    :class:`CLIPlugin` instead.

    Keep in mind that right now the decorated function must use `**kwargs` as
    param, as it will be passed all the members of the parser, not just
    whatever it defined
    """
    def __init__(self, do_run=None):
        self._help = None
        self._parser_args = []
        self._do_run = do_run

    @property
    def help(self):
        return (
            self._help
            if self._help is not None
            else self._do_run.__doc__
        )

    def set_help(self, help):
        self._help = help

    def add_argument(self, *argument_args, **argument_kwargs):
        self._parser_args.append((argument_args, argument_kwargs))

    def populate_parser(self, parser):
        for argument_args, argument_kwargs in self._parser_args:
            parser.add_argument(*argument_args, **argument_kwargs)

    def do_run(self, args):
        self._do_run(**vars(args))

    def __call__(self, *args, **kwargs):
        """
        Keep the original function interface, so it can be used elsewhere
        """
        return self._do_run(*args, **kwargs)


def cli_plugin_add_argument(*args, **kwargs):
    """
    Decorator generator that adds an argument to the cli plugin based on the
    decorated function

    Args:
        *args: Any args to be passed to
            :func:`argparse.ArgumentParser.add_argument`
        *kwargs: Any keyword args to be passed to
            :func:`argparse.ArgumentParser.add_argument`


    Returns:
        function: Decorator that builds or extends the cliplugin for the
            decorated function, adding the given argument definition

    Examples:
        >>> @cli_plugin_add_argument('-m', '--mogambo', action='store_true')
        ... def test(**kwargs):
        ...     print 'test'
        ...
        >>> print test.__class__
        <class 'cli.CLIPluginFuncWrapper'>
        >>> print test._parser_args
        [(('-m', '--mogambo'), {'action': 'store_true'})]

        >>> @cli_plugin_add_argument('-m', '--mogambo', action='store_true')
        ... @cli_plugin_add_argument('-b', '--bogabmo', action='store_false')
        ... @cli_plugin
        ... def test(**kwargs):
        ...     print 'test'
        ...
        >>> print test.__class__
        <class 'cli.CLIPluginFuncWrapper'>
        >>> print test._parser_args # doctest: +NORMALIZE_WHITESPACE
        [(('-b', '--bogabmo'), {'action': 'store_false'}),
         (('-m', '--mogambo'), {'action': 'store_true'})]

    """
    def decorator(func):
        if not isinstance(func, CLIPluginFuncWrapper):
            func = CLIPluginFuncWrapper(do_run=func)

        func.add_argument(*args, **kwargs)
        return func

    return decorator


def cli_plugin_add_help(help):
    """
    Decorator generator that adds the cli help to the cli plugin based on the
    decorated function

    Args:
        help (str): help string for the cli plugin

    Returns:
        function: Decorator that builds or extends the cliplugin for the
            decorated function, setting the given help
    Examples:
        >>> @cli_plugin_add_help('my help string')
        ... def test(**kwargs):
        ...     print 'test'
        ...
        >>> print test.__class__
        <class 'cli.CLIPluginFuncWrapper'>
        >>> print test.help
        my help string

        >>> @cli_plugin_add_help('my help string')
        ... @cli_plugin()
        ... def test(**kwargs):
        ...     print 'test'
        >>> print test.__class__
        <class 'cli.CLIPluginFuncWrapper'>
        >>> print test.help
        my help string
    """

    def decorator(func):

        if not isinstance(func, CLIPluginFuncWrapper):
            func = CLIPluginFuncWrapper(do_run=func)

        func.set_help(help)
        return func

    return decorator


def cli_plugin(func=None):
    """
    Decorator that wraps the given function in a :class:`CLIPlugin`

    Args:
        func (callable): function/class to decorate

    Returns:
        CLIPlugin: cli plugin that handles that method

    Notes:
        It can be used as a decorator or as a decorator generator, if used as a
        decorator generator don't pass any parameters

    Examples:
        >>> @cli_plugin
        ... def test(**kwargs):
        ...     print 'test'
        ...
        >>> print test.__class__
        <class 'cli.CLIPluginFuncWrapper'>

        >>> @cli_plugin()
        ... def test(**kwargs):
        ...     print 'test'
        >>> print test.__class__
        <class 'cli.CLIPluginFuncWrapper'>
    """
    # this allows calling this function as a decorator generator
    if func is None:
        return cli_plugin

    return CLIPluginFuncWrapper(do_run=func)
