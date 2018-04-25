import logging
import functools
from lago import log_utils, utils
from collections import namedtuple

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
Command = namedtuple('Command', ['name', 'cmd'])


class Build(object):
    """
    A Build object represents a build section in the init file.
    Each build section (which in turn belongs to a specific disk)
    should get his own Build object

    In order to add support for a new build command, a new function with
    the name of the command should be implemented in this class. this function
    should accept a list of options and arguments and return a named tuple
    'Command', where 'Command.name' is the name of the command and
    'Command.cmd' is the a list containing the command and its args,
    for example:
    Command.name = 'virt-customize'
    Command.cmd = ['virt-customize', '-a', PATH_TO_DISK, SOME_CMDS...]

    Attributes:
        name (str): The name of the vm this builder belongs
        disk_path (str): The path to the disk that needs to be customized
        paths (lago.paths.Paths): The paths of the current prefix
        build_cmds (list of str): A list of commands that should
            be invoked on the disk
            located in disk_path
    """

    @staticmethod
    def normalize_options(options):
        """
        Turns a mapping of 'option: arg' to a list and prefix the options.
        arg can be a list of arguments.

        for example:

        dict = {
            o1: a1,
            o2: ,
            o3: [a31, a32]
            o4: []
        }

        will be transformed to:

        [
            prefix_option(o1), a1, prefix_option(o2),
            prefix_option(o3), a31, prefix_option(o3), a32
            prefix_option(o4)
        ]

        note that empty arguments are omitted

        Args:
            options (dict): A mapping between options and arguments

        Returns:
            lst: A normalized version of 'options' as mentioned above
        """
        normalized_options = []

        def _add(option, arg=None):
            normalized_options.append(option)
            arg and normalized_options.append(arg)

        for option, arg in options.viewitems():
            prefixed_option = Build.prefix_option(option)
            if isinstance(arg, list) and arg:
                for a in arg:
                    _add(prefixed_option, a)
            else:
                _add(prefixed_option, arg)

        return normalized_options

    @staticmethod
    def prefix_option(option):
        """
        Depends on the option's length, prefix it with '-' or '--'
        Args:
            option (str): The option to prefix
        Returns:
            str: prefixed option
        """
        if len(option) == 1:
            return '-{}'.format(option)
        else:
            return '--{}'.format(option)

    @classmethod
    def get_instance_from_build_spec(cls, name, disk_path, build_spec, paths):
        """
        Args:
            name (str): The name of the vm this builder belongs
            disk_path (str): The path to the disk that needs to be customized
            paths (lago.paths.Paths): The paths of the current prefix
            build_spec (dict): The build spec part, associated with the
                disk located at disk_path, from the init file.

        Returns:
            An instance of Build with a normalized build spec i.e ready to
                be invoked.
        """
        instance = cls(name, disk_path, paths)
        instance.normalize_build_spec(build_spec)
        return instance

    def __init__(self, name, disk_path, paths):
        self.name = name
        self.disk_path = disk_path
        self.paths = paths
        self.build_cmds = []

    def normalize_build_spec(self, build_spec):
        """
        Convert a build spec into a list of Command tuples.
        After running this command, self.build_cmds should hold all
        the commands that should be run on the disk in self.disk_path.

        Args:
            build_spec (dict): The buildspec part from the init file
        """
        for cmd in build_spec:
            if not cmd:
                continue
            cmd_name = cmd.keys()[0]
            cmd_options = cmd.values()[0]
            cmd_handler = self.get_cmd_handler(cmd_name)
            self.build_cmds.append(cmd_handler(cmd_options))

    def get_cmd_handler(self, cmd):
        """
        Return an handler for cmd.
        The handler and the command should have the same name.
        See class description for more info about handlers.

        Args:
            cmd (str): The name of the command

        Returns:
            callable: which handles cmd

        Raises:
            lago.build.BuildException: If an handler for cmd doesn't exist
        """
        cmd = cmd.replace('-', '_')
        handler = getattr(self, cmd, None)
        if not handler:
            raise BuildException(
                'Command {} is not supported as a '
                'build command'.format(cmd)
            )
        return handler

    def virt_customize(self, options):
        """
        Handler for 'virt-customize'
        note: if 'ssh-inject' option was specified without a path to a key,
        the prefix' key will be copied to the vm.

        Args:
            options (lst of str): Options and arguments for 'virt-customize'

        Returns:
            callable: which handles cmd

        Raises:
            lago.build.BuildException: If an handler for cmd doesn't exist
        """
        cmd = ['virt-customize', '-a', self.disk_path]
        if 'ssh-inject' in options and not options['ssh-inject']:
            options['ssh-inject'] = 'root:file:{}'.format(
                self.paths.ssh_id_rsa_pub()
            )

        options = self.normalize_options(options)
        cmd.extend(options)
        return Command('virt-customize', cmd)

    def build(self):
        """
        Run all the commands in self.build_cmds

        Raises:
            lago.build.BuildException: If a command returned a non-zero code
        """
        if not self.build_cmds:
            LOGGER.debug('No build commands were found, skipping build step')

        with LogTask('Building {} disk {}'.format(self.name, self.disk_path)):
            for command in self.build_cmds:
                with LogTask('Running command {}'.format(command.name)):
                    LOGGER.debug(command.cmd)
                    result = utils.run_command(command.cmd)
                    if result:
                        raise BuildException(result.err)


class BuildException(utils.LagoException):
    pass
