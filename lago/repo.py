from lago.cmd import in_lago_prefix
from lago.plugins.cli import (CLIPlugin, cli_plugin_add_argument)
from lago.plugins.repo import RepoPluginUserError
from lago.repo_utils import (
    generate_repo, remove_sections_by_pattern, add_to_conf,
    strip_excludes_from_conf, collect_values, add_option_to_sections
)
from lago.utils import with_logging
import configparser
import functools
import lago.plugins
import lago.plugins.repo as repo_plugin
import logging
import log_utils
import prefix
import StringIO

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)


class Yum(repo_plugin.RepoPlugin):

    # Maybe add it to the config file
    config_dir = '/etc/yum.conf'

    def __init__(self, vm):
        super(Yum, self).__init__(vm)
        self.guest_config = None
        self._get_guest_conf()

    def _get_guest_conf(self):
        LOGGER.debug('Reading repo conf from {}'.format(self.vm.name()))
        result = self.vm.ssh(['cat', self.config_dir])
        # TODO: add error checking
        result = unicode(result.out)
        self.guest_config = configparser.ConfigParser()
        self.guest_config.read_string(result)

    def _set_guest_conf(self):
        with LogTask('Writing repo conf to {}'.format(self.vm.name())):
            string_io = StringIO.StringIO()
            self.guest_config.write(string_io, space_around_delimiters=False)
            cmd = 'echo "{}"'.format(string_io.getvalue())
            # TODO: add error checking
            result = self.vm.ssh([cmd, '> {}'.format(self.config_dir)])

    def add_local_repo(self, url=None, inject=False, *args, **kwargs):
        with LogTask('Adding local repo to {}'.format(self.vm.name())):
            if (not url) and (not self.mgmt_nets):
                raise RepoPluginUserError(
                    'url was not specified and no management network '
                    'could be found, please specify the url of the local repo'
                )

            # TODO: Take default repo port from config
            url = url or 'http://{}:8585/{}'.format(
                self.mgmt_nets.pop().gw(), self.vm.distro()
            )
            # TODO: Take repo specs from cmd
            repo = generate_repo(
                'local_repo', url, enabled=1, gpgcheck='0', cost='1'
            )

            if inject:
                self.guest_config = remove_sections_by_pattern(
                    self.guest_config, r'^main$', negative=True
                )
                self.guest_config.set('main', 'reposdir', '/dev/null')

            self.guest_config = add_to_conf(self.guest_config, repo)
            self._set_guest_conf()

    def add(self, config, strip_excludes, set_exclusive, *args, **kwargs):
        other_config = configparser.ConfigParser()
        other_config.read(config)

        if strip_excludes:
            strip_excludes_from_conf(other_config)

        if set_exclusive:
            include_set = collect_values(other_config, 'includepkgs')
            add_option_to_sections(
                self.guest_config,
                'exclude',
                ' '.join(include_set),
                pattern=r'^main$',
                negative=True
            )

        self.guest_config = add_to_conf(self.guest_config, other_config)
        self._set_guest_conf()

    def inject(self, config, strip_excludes, *args, **kwargs):
        other_config = configparser.ConfigParser()
        other_config.read(config)
        if strip_excludes:
            strip_excludes_from_conf(other_config)

        self.guest_config = other_config
        self._set_guest_conf()

    def inject_local_repo(self, url, *args, **kwargs):
        self.add_local_repo(url, inject=True)


class Dnf(Yum):
    pass


def pkg_managers(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        managers = [
            repo_plugin.get_cls_by_distro(vm.distro())(vm)
            for vm in kwargs['vms']
        ]
        kwargs['pkg_managers'] = managers
        return func(*args, **kwargs)

    return wrapper


@lago.plugins.cli.cli_plugin(
    help='Inject the given full configuration to a vm, '
    'Overriding all other configuration.'
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--vm-names',
    help='The names of the vms which this command is going to effect.'
    'if no name is specified, this command is going to effect on '
    'all the vms in the prefix',
    nargs='*',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--strip-excludes',
    help='Strips exclude directives from configuration before adding.',
    action='store_true',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'config',
    help='The config to inject. could be a string or a file',
)
@in_lago_prefix
@prefix.get_vms
@with_logging
@pkg_managers
def do_inject(prefix, pkg_managers, config, strip_excludes, **kwargs):
    for manager in pkg_managers:
        with LogTask('Injecting repo config to {}'.format(manager.vm.name())):
            manager.inject(config, strip_excludes)


@lago.plugins.cli.cli_plugin(
    help='Add the given yum configuration to the guest existing configuration'
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--vm-names',
    help='The names of the vms which this command is going to effect.'
    'if no name is specified, this command is going to effect on '
    'all the vms in the prefix',
    nargs='*',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--strip-excludes',
    help='Strips exclude directives from configuration before adding.',
    action='store_true',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--set-exclusive',
    help='Insures that all packages that are included in the added repos '
    'are excluded from all the guest pre-existing repos',
    action='store_true',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'config',
    help='The config to inject. could be a string or a file',
)
@in_lago_prefix
@prefix.get_vms
@with_logging
@pkg_managers
def do_add(
    prefix, pkg_managers, config, strip_excludes, set_exclusive, **kwargs
):
    for manager in pkg_managers:
        with LogTask('Adding repo config to {}'.format(manager.vm.name())):
            manager.add(config, strip_excludes, set_exclusive)


@lago.plugins.cli.cli_plugin(
    help='Replace all guest yum configuration with a configuration that only '
    'includes a local repository'
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--url',
    help='The url of the local repo',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--vm-names',
    help='The names of the vms which this command is going to effect.'
    'if no name is specified, this command is going to effect on '
    'all the vms in the prefix',
    nargs='*',
)
@in_lago_prefix
@prefix.get_vms
@with_logging
@pkg_managers
def do_inject_local_repo(prefix, pkg_managers, url, **kwargs):
    for manager in pkg_managers:
        with LogTask(
            'Injecting local repo config to {}'.format(manager.vm.name())
        ):
            manager.inject_local_repo(url)


@lago.plugins.cli.cli_plugin(
    help='Add local repository to guest existing configuration'
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--url',
    help='The url of the local repo',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--vm-names',
    help='The names of the vms which this command is going to effect.'
    'if no name is specified, this command is going to effect on '
    'all the vms in the prefix',
    nargs='*',
)
@in_lago_prefix
@prefix.get_vms
@with_logging
@pkg_managers
def do_add_local_repo(prefix, pkg_managers, url, **kwargs):
    for manager in pkg_managers:
        with LogTask(
            'Adding local repo config to {}'.format(manager.vm.name())
        ):
            manager.add_local_repo(url)


def _populate_parser(cli_plugins, parser):
    verbs_parser = parser.add_subparsers(
        dest='repoverb',
        metavar='VERB',
    )
    for cli_plugin_name, plugin in cli_plugins.items():
        plugin_parser = verbs_parser.add_parser(
            cli_plugin_name, **plugin.init_args
        )
        plugin.populate_parser(plugin_parser)

    return parser


class RepoCLIPlugin(CLIPlugin):
    def populate_parser(self, parser):
        self.cli_plugins = lago.plugins.load_plugins('lago.plugins.repo.cli')
        _populate_parser(self.cli_plugins, parser)

    def do_run(self, args):
        self.cli_plugins[args.repoverb].do_run(args)

    @property
    def init_args(self):
        return {'help': 'Manage vm repositories'}
