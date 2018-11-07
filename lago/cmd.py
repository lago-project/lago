#!/usr/bin/env python2
#
# Copyright 2014-2017 Red Hat, Inc.
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
from __future__ import print_function

import argparse
import logging
import os
import pkg_resources
import sys
from textwrap import dedent
import warnings
from signal import signal, SIGTERM, SIGHUP

import lago
import lago.plugins
import lago.plugins.cli
import lago.templates
from lago.config import config
from lago import (log_utils, workdir as lago_workdir, utils, lago_ansible)
from lago.utils import (in_prefix, with_logging, LagoUserException)

LOGGER = logging.getLogger('cli')
in_lago_prefix = in_prefix(
    prefix_class=lago.prefix.Prefix,
    workdir_class=lago_workdir.Workdir,
)


@lago.plugins.cli.cli_plugin(
    help='Initialize a directory for framework deployment'
)
@lago.plugins.cli.cli_plugin_add_argument(
    'virt_config',
    help=(
        'Configuration of resources to deploy, json and yaml file formats '
        'are supported, takes option precedence over workdir. Will use '
        '$PWD/LagoInitFile by default. You can use any env vars in that file, '
        'inculuding the extra ones LAGO_PREFIX_PATH LAGO_WORKDIR_PATH and '
        'LAGO_INITFILE_PATH'
    ),
    metavar='VIRT_CONFIG',
    type=os.path.abspath,
    nargs='?',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'workdir',
    help=(
        'Workdir directory of the deployment, if none passed, it will use '
        '$PWD/.lago'
    ),
    metavar='WORKDIR',
    type=os.path.abspath,
    nargs='?',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--template-repo-path',
    help='Repo file describing the templates',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--template-repo-name',
    help='Name of the repo from the template repos dir',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--template-store',
    help='Location to store templates at',
    type=os.path.abspath,
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--template-repos',
    help='Location to store repos',
    type=os.path.abspath,
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--set-current',
    action='store_true',
    help='If passed, it will set the newly created prefix as the current one',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--skip-bootstrap',
    action='store_true',
    help=(
        'If passed, will skip bootstrapping the images, useful if you are '
        'using templates and you already know they will have the correct '
        'root pass for example'
    ),
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--skip-build',
    action='store_true',
    help=(
        'If passed, will skip the build commands specified in the build'
        'section of all the disks'
    ),
)
def do_init(
    workdir,
    virt_config,
    prefix_name='default',
    template_repo_path=None,
    template_repo_name=None,
    template_store=None,
    template_repos=None,
    set_current=False,
    skip_bootstrap=False,
    skip_build=False,
    **kwargs
):

    if virt_config is None and workdir is not None:
        virt_config = workdir
        workdir = None

    if workdir is None:
        workdir = os.path.abspath('.lago')

    if virt_config is None:
        virt_config = os.path.abspath('LagoInitFile')
    if not os.path.isfile(virt_config):
        raise LagoUserException(
            'Unable to find init file: {0}'.format(virt_config)
        )

    os.environ['LAGO_INITFILE_PATH'] = os.path.dirname(
        os.path.abspath(virt_config)
    )

    if prefix_name == 'current':
        prefix_name = 'default'

    with log_utils.LogTask('Initialize and populate prefix', LOGGER):
        LOGGER.debug('Using workdir %s', workdir)
        workdir = lago_workdir.Workdir(workdir)
        if not (
            os.path.exists(workdir.path)
            and lago.workdir.Workdir.is_workdir(workdir.path)
        ):
            LOGGER.debug(
                'Initializing workdir %s with prefix %s',
                workdir.path,
                prefix_name,
            )
            prefix = workdir.initialize(prefix_name)
        else:
            LOGGER.debug(
                'Adding prefix %s to workdir %s',
                prefix_name,
                workdir.path,
            )
            prefix = workdir.add_prefix(prefix_name)

        log_utils.setup_prefix_logging(prefix.paths.logs())

        try:
            if template_repo_path:
                repo = lago.templates.TemplateRepository.from_url(
                    template_repo_path
                )
            elif template_repo_name:
                repo = lago.templates.find_repo_by_name(
                    name=template_repo_name
                )

            else:
                raise RuntimeError(
                    'No template repo was configured or specified'
                )

            store = lago.templates.TemplateStore(template_store)

            with open(virt_config, 'r') as virt_fd:
                prefix.virt_conf_from_stream(
                    virt_fd,
                    repo,
                    store,
                    do_bootstrap=not skip_bootstrap,
                    do_build=not skip_build,
                )

            if set_current:
                workdir.set_current(new_current=prefix_name)

        except:
            workdir.cleanup()
            raise

        return workdir, prefix


@lago.plugins.cli.cli_plugin(help='Clean up deployed resources')
@in_lago_prefix
@with_logging
def do_cleanup(prefix, **kwargs):
    prefix.cleanup()


@lago.plugins.cli.cli_plugin(
    help='Cleanup and remove the whole prefix and any files in it'
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--all-prefixes',
    help="Destroy all the prefixes in the workdir",
    action='store_true',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '-y',
    '--yes',
    help="Don't ask for confirmation, assume yes",
    action='store_true',
)
@in_lago_prefix
@with_logging
def do_destroy(
    prefix, yes, all_prefixes, parent_workdir, prefix_name, **kwargs
):

    if all_prefixes:
        warn_message = 'all the prefixes under ' + parent_workdir.path
        path = parent_workdir.path
    else:
        warn_message = prefix.paths.prefix_path()
        path = warn_message

    if not yes:
        response = raw_input(
            'Do you really want to destroy %s? [Yn] ' % warn_message
        )
        if response and response[0] not in 'Yy':
            LOGGER.info('Aborting on user input')
            return

    if os.path.islink(path):
        os.unlink(path)
        return

    if all_prefixes:
        parent_workdir.destroy()
    elif parent_workdir:
        parent_workdir.destroy([prefix_name])
    else:
        prefix.destroy()


@lago.plugins.cli.cli_plugin(help='Deploy lago resources')
@lago.plugins.cli.cli_plugin_add_argument(
    'vm_names',
    help='Name of the vm to start',
    metavar='VM_NAME',
    nargs='*',
)
@in_lago_prefix
@with_logging
def do_start(prefix, vm_names=None, **kwargs):
    prefix.start(vm_names=vm_names)


@lago.plugins.cli.cli_plugin(help='Destroy lago resources')
@lago.plugins.cli.cli_plugin_add_argument(
    'vm_names',
    help='Name of the vm to stop',
    metavar='VM_NAME',
    nargs='*',
)
@in_lago_prefix
@with_logging
def do_stop(prefix, vm_names, **kwargs):
    prefix.stop(vm_names=vm_names)


@lago.plugins.cli.cli_plugin(
    help='Shutdown and destroy, or reboot vms',
    description='This command will shutdown or reboot the given vms. '
    'Networks that will not have running vms connected to them after '
    'running this command will be stopped as well.'
)
@lago.plugins.cli.cli_plugin_add_argument(
    '-r',
    '--reboot',
    help='If specified, reboot the requested vms',
    action='store_true',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'vm_names',
    help='Name of the vms to shutdown',
    metavar='VM_NAME',
    nargs='*',
)
@in_lago_prefix
@with_logging
def do_shutdown(prefix, vm_names, reboot, **kwargs):
    prefix.shutdown(vm_names, reboot)


@lago.plugins.cli.cli_plugin(
    help='Export virtual machine disks',
    description='This command will export the disks of the given vms. '
    'The disks of the vms will be exported to the '
    'current directory or to the path that was specified with "-d". '
    'If "-s" was specified, the disks will be exported as '
    '"standalone disk", which means that they will be merged with their '
    'base images. This command does not modifying the source disk. '
    'The env should be in "down" state when running this command.'
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--vm-names',
    '-n',
    help='Name of the vms to export. If no name is specified, export all '
    'the vms in this prefix.',
    metavar='VM_NAME',
    nargs='*',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--standalone',
    '-s',
    help='If not specified, export a layered image',
    action='store_true',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--compress',
    '-c',
    help='If specified, compress the exported images with xz',
    action='store_true',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--dst-dir',
    '-d',
    default='.',
    help='Dir to place the exported images in',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--init-file-name',
    default='LagoInitFile',
    help='The name of the exported init file',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--collect-only',
    action='store_true',
    help='Only output the disks that will be exported',
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--without-threads',
    action='store_true',
    help='If set, do not use threads',
)
@in_lago_prefix
@with_logging
def do_export(
    prefix, vm_names, standalone, dst_dir, compress, init_file_name,
    out_format, collect_only, without_threads, **kwargs
):
    output = prefix.export_vms(
        vm_names, standalone, dst_dir, compress, init_file_name, out_format,
        collect_only, not without_threads
    )
    if collect_only:
        print(out_format.format(output))


@lago.plugins.cli.cli_plugin(
    help='Create snapshots for all deployed resources'
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--list',
    '-l',
    dest='list_only',
    help='List current available snapshots',
    action='store_true',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'snapshot_name',
    help='Name of the snapshot to create',
    metavar='SNAPSHOT_NAME',
    nargs='?',
    default=None,
)
@in_lago_prefix
@with_logging
def do_snapshot(prefix, list_only, snapshot_name, out_format, **kwargs):
    if list_only:
        snapshots = prefix.get_snapshots()
        print(out_format.format(snapshots))
    elif snapshot_name:
        prefix.create_snapshots(snapshot_name)
    else:
        raise RuntimeError('No snapshot name provided')


@lago.plugins.cli.cli_plugin(help='Revert resources to a snapshot')
@lago.plugins.cli.cli_plugin_add_argument(
    'snapshot_name',
    help='Name of the snapshot to revert to',
    metavar='SNAPSHOT_NAME',
)
@in_lago_prefix
@with_logging
def do_revert(prefix, snapshot_name, **kwargs):
    prefix.revert_snapshots(snapshot_name)


@lago.plugins.cli.cli_plugin(
    help='Open shell on the domain or run as script/command',
    prefix_chars='\x00',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'args',
    help=(
        'If none provided, an interactive shell will be started.\n'
        'If arguments start with -c, what follows will be '
        'executes as a command.\n'
        'Otherwise, if a single provided, it will be ran as script'
        ' on the domain.'
    ),
    nargs='*',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'host',
    help='Host to connect to',
    metavar='HOST',
)
@in_lago_prefix
@with_logging
def do_shell(prefix, host, args=None, **kwargs):
    args = args or []
    try:
        host = prefix.virt_env.get_vm(host)
    except KeyError:
        ssh_host = None
        for possible_host in prefix.virt_env.get_vms():
            if possible_host.endswith(host):
                ssh_host = prefix.virt_env.get_vm(possible_host)
                break
        if ssh_host:
            host = ssh_host
        else:
            LOGGER.error('Unable to find VM %s', host)
            LOGGER.info(
                'Available VMs:\n\t' +
                '\n\t'.join(prefix.virt_env.get_vms().keys())
            )
            raise

    if not host.running():
        raise RuntimeError(
            'Host %s is not "running", but "%s"' % (host.name(), host.state())
        )

    host.wait_for_ssh()

    if len(args) == 0:
        result = host.interactive_ssh(['bash'])
    elif len(args) == 1 and os.path.isfile(args[0]):
        result = host.ssh_script(args[0])
    else:
        if args[0] == '-c':
            args = args[1:]

        result = host.interactive_ssh(args)

    sys.exit(result.code)


@lago.plugins.cli.cli_plugin(
    help='Open serial console to the domain',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'host',
    help='Host to connect to',
    metavar='HOST',
)
@in_lago_prefix
@with_logging
def do_console(prefix, host, **kwargs):
    try:
        host = prefix.virt_env.get_vm(host)
    except KeyError:
        LOGGER.error('Unable to find VM %s', host)
        LOGGER.info(
            'Available VMs:\n\t' +
            '\n\t'.join(prefix.virt_env.get_vms().keys())
        )
        raise

    result = host.interactive_console()
    sys.exit(result.code)


@lago.plugins.cli.cli_plugin(
    help='Create Ansible host inventory of the environment',
    description=dedent(
        """
    This method iterates through all the VMs and creates an Ansible
    host inventory. For each vm it defines an IP address and a private key.

    The default groups are based on the values which associated
    with the following keys: 'vm-type', 'groups', 'vm-provider'.

    The 'keys' parameter can be used to override the default groups,
    for example to create a group which based on a 'service_provider',
    --keys 'service_provider' should be added to this command.

    Nested keys can be used also by specifying the path to the key,
    for example '/disks/0/metadata/distro' will create a group based on the
    distro of the os installed on disk at position 0 in the init file.
    (we assume that numeric values in the path should be used as index for
    list access).

    If the value associated with the key is a list, a group will be created
    for every item in that list (this is useful when you want to associate
    a machine with more than one group).

    The output of this command is printed to standard output.

    Example of a possible output:

    lago ansible_hosts -k 'vm-type'

    [vm-type=ovirt-host]
    lago-host1 ansible_host=1.2.3.4 ansible_ssh_private_key_file=/path/rsa
    lago-host2 ansible_host=1.2.3.6 ansible_ssh_private_key_file=/path/rsa
    [vm-type=ovirt-engine]
    lago-engine ansible_host=1.2.3.5 ansible_ssh_private_key_file=/path/rsa

    lago ansible_hosts -k 'disks/0/metadata/arch' 'groups'

    [disks/0/metadata/arch=x86_64]
    vm0-server ansible_host=1.2.3.4 ansible_ssh_private_key_file=/path/rsa
    vm1-slave ansible_host=1.2.3.5 ansible_ssh_private_key_file=/path/rsa
    vm2-slave ansible_host=1.2.3.6 ansible_ssh_private_key_file=/path/rsa
    [groups=slaves]
    vm1-slave ansible_host=1.2.3.5 ansible_ssh_private_key_file=/path/rsa
    vm2-slave ansible_host=1.2.3.6 ansible_ssh_private_key_file=/path/rsa
    [groups=servers]
    vm0-server ansible_host=1.2.3.4 ansible_ssh_private_key_file=/path/rsa
    """
    )
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--keys',
    '-k',
    help='Path to the keys that should be used as groups',
    default=['vm-type', 'groups', 'vm-provider'],
    metavar='KEY',
    nargs='*',
)
@in_lago_prefix
@with_logging
def do_generate_ansible_hosts(prefix, keys, **kwargs):
    print(lago_ansible.LagoAnsible(prefix).get_inventory_str(keys))


@lago.plugins.cli.cli_plugin(
    help='Show status of the deployed virtual resources'
)
@in_lago_prefix
@with_logging
def do_status(prefix, out_format, **kwargs):

    with open(prefix.paths.uuid()) as f:
        uuid = f.read()

    info_dict = {
        'Prefix':
            {
                'Base directory':
                    prefix.paths.prefix_path(),
                'UUID':
                    uuid,
                'Networks':
                    dict(
                        (
                            net.name(), {
                                'gateway': net.gw(),
                                'status': net.alive() and 'up' or 'down',
                                'management': net.is_management(),
                            }
                        ) for net in prefix.virt_env.get_nets().values()
                    ),
                'VMs':
                    dict(
                        (
                            vm.name(), {
                                'distro':
                                    vm.distro(),
                                'root password':
                                    vm.root_password(),
                                'status':
                                    vm.state(),
                                'snapshots':
                                    ', '.join(vm._spec['snapshots'].keys()),
                                'metadata':
                                    vm.metadata,
                                'NICs':
                                    dict(
                                        (
                                            'eth%d' % i, {
                                                'network': nic['net'],
                                                'ip': nic.get('ip', 'N/A'),
                                            }
                                        ) for i, nic in enumerate(vm.nics())
                                    ),
                            }
                        ) for vm in prefix.virt_env.get_vms().values()
                    ),
            },
    }

    print(out_format.format(info_dict))


@lago.plugins.cli.cli_plugin(help='List the prefixes (envs) in a Workdir')
@lago.plugins.cli.cli_plugin_add_argument(
    'workdir_path',
    help=dedent(
        """
        Path to the Workdir. If not provided Lago will
        try to find a Workdir relative to the current directory.
        """
    ),
    metavar='WORKDIR_PATH',
    type=os.path.abspath,
    nargs='?',
)
def do_list(workdir_path, out_format, **kwargs):
    if not workdir_path:
        workdir_path = lago_workdir.Workdir.resolve_workdir_path()

    workdir = lago_workdir.Workdir(path=workdir_path)
    workdir.load()
    resources = workdir.prefixes.keys()

    print(out_format.format(resources))


@lago.plugins.cli.cli_plugin(
    help='Copy file from a virtual machine to local machine'
)
@lago.plugins.cli.cli_plugin_add_argument(
    'local_path',
    help='Path on the local host to copy the file/dir to',
    metavar='LOCAL_PATH',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'remote_path',
    help='Path of the file/dir to copy from the host',
    metavar='REMOTE_PATH',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'host',
    help='Host to copy files from',
    metavar='HOST',
)
@in_lago_prefix
@with_logging
def do_copy_from_vm(prefix, host, remote_path, local_path, **kwargs):
    try:
        host = prefix.virt_env.get_vm(host)
    except KeyError:
        LOGGER.error('Unable to find VM %s', host)
        LOGGER.info(
            'Available VMs:\n\t' +
            '\n\t'.join(prefix.virt_env.get_vms().keys())
        )
        raise

    if not host.running():
        raise RuntimeError(
            'Host %s is not "running", but "%s"' % (host.name(), host.state())
        )

    host.wait_for_ssh()
    host.copy_from(remote_path, local_path)


@lago.plugins.cli.cli_plugin(
    help='Copy file/dir to a virtual machine from the local host'
)
@lago.plugins.cli.cli_plugin_add_argument(
    'remote_path',
    help='Local path to copy the file/dir to',
    metavar='REMOTE_PATH',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'local_path',
    help='Path of the file/dir to copy from the host',
    metavar='LOCAL_PATH',
)
@lago.plugins.cli.cli_plugin_add_argument(
    'host',
    help='Host to copy files to',
    metavar='HOST',
)
@in_lago_prefix
@with_logging
def do_copy_to_vm(prefix, host, remote_path, local_path, **kwargs):
    try:
        host = prefix.virt_env.get_vm(host)
    except KeyError:
        LOGGER.error('Unable to find VM %s', host)
        LOGGER.info(
            'Available VMs:\n\t' +
            '\n\t'.join(prefix.virt_env.get_vms().keys())
        )
        raise

    if not host.running():
        raise RuntimeError(
            'Host %s is not "running", but "%s"' % (host.name(), host.state())
        )

    host.wait_for_ssh()
    host.copy_to(local_path, remote_path)


@lago.plugins.cli.cli_plugin(
    help=(
        'Collect logs from VMs, list of collected logs '
        'can be specified in the init file, under '
        'artifacts parameter '
    )
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--output',
    help='Path to place all the extracted at',
    required=True,
    type=os.path.abspath,
)
@lago.plugins.cli.cli_plugin_add_argument(
    '--no-skip',
    help='do not skip missing paths',
    action='store_true',
)
@in_lago_prefix
@with_logging
def do_collect(prefix, output, no_skip, **kwargs):
    prefix.collect_artifacts(output, ignore_nopath=not no_skip)


@lago.plugins.cli.cli_plugin(
    help='Run scripts that install necessary RPMs and configuration'
)
@in_lago_prefix
@with_logging
def do_deploy(prefix, **kwargs):
    prefix.deploy()


@lago.plugins.cli.cli_plugin(help="Dump configuration file")
@lago.plugins.cli.cli_plugin_add_argument(
    '--verbose',
    help='Include parameters with no default value.',
    action='store_true',
    default=False,
)
def do_generate(verbose, **kwargs):
    print(config.get_ini(incl_unset=verbose))


def create_parser(cli_plugins, out_plugins):
    parser = argparse.ArgumentParser(
        description='Command line interface to Lago',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )
    parser.add_argument(
        '-l',
        '--loglevel',
        choices=['info', 'debug', 'error', 'warning'],
        help='Log level to use'
    )
    parser.add_argument(
        '--logdepth', type=int, help='How many task levels to show'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='%(prog)s ' + pkg_resources.get_distribution("lago").version,
    )
    parser.add_argument(
        '--out-format',
        '-f',
        action='store',
        default='default',
        choices=out_plugins.keys(),
    )
    parser.add_argument(
        '--prefix-path',
        '-p',
        action='store',
        default=None,
        help=(
            'Path to the prefix to use, will be deprecated, use '
            '--workdir-path instead'
        ),
    )
    parser.add_argument(
        '--workdir-path',
        '-w',
        action='store',
        default=None,
        help='Path to the workdir to use.',
    )
    parser.add_argument(
        '--prefix-name',
        '-P',
        action='store',
        help='Name of the prefix to use.',
    )
    parser.add_argument(
        '--ssh-user',
        action='store',
        help='User for SSH provider.',
    )
    parser.add_argument(
        '--ssh-password',
        action='store',
        help='Password for SSH provider.',
    )
    parser.add_argument(
        '--ssh-tries',
        action='store',
        type=int,
        help='Number of ssh time outs to wait before failing.',
    )
    parser.add_argument(
        '--ssh-timeout',
        action='store',
        type=int,
        help='Seconds to wait before marking SSH connection as failed.'
    )
    parser.add_argument(
        '--libvirt_url',
        action='store',
        help='libvirt URI, currently only '
        'system'
        ' is supported.'
    )
    parser.add_argument(
        '--libvirt-user',
        action='store',
        help='libvirt user',
    )
    parser.add_argument(
        '--libvirt-password',
        action='store',
        help='libvirt password',
    )
    parser.add_argument(
        '--default_vm_type',
        action='store',
        help='Default vm type',
    )

    parser.add_argument(
        '--default_vm_provider',
        action='store',
        help='Default vm provider',
    )
    parser.add_argument(
        '--default_root_password',
        action='store',
        help='Default root password',
    )
    parser.add_argument(
        '--lease_dir',
        action='store',
        help='Path to store created subnets configurations'
    )
    parser.add_argument(
        '--reposync-dir',
        action='store',
        help='Reposync dir if used',
    )

    parser.add_argument('--ignore-warnings', action='store_true')
    parser.set_defaults(**config.get_section('lago', {}))
    verbs_parser = parser.add_subparsers(dest='verb', metavar='VERB')
    for cli_plugin_name, cli_plugin in cli_plugins.items():
        plugin_parser = verbs_parser.add_parser(
            name=cli_plugin_name,
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            **cli_plugin.init_args
        )
        cli_plugin.populate_parser(plugin_parser)
        plugin_parser.set_defaults(**config.get_section(cli_plugin_name, {}))
    config.update_parser(parser=parser)

    return parser


def exit_handler(signum, frame):
    """
    Catch SIGTERM and SIGHUP and call "sys.exit" which raises
    "SystemExit" exception.
    This will trigger all the cleanup code defined in ContextManagers
    and "finally" statements.

    For more details about the arguments see "signal" documentation.

    Args:
        signum(int): The signal's number
        frame(frame): The current stack frame, can be None
    """

    LOGGER.debug('signal {} was caught'.format(signum))
    sys.exit(128 + signum)


def main():

    # Trigger cleanup on SIGTERM and SIGHUP
    signal(SIGTERM, exit_handler)
    signal(SIGHUP, exit_handler)

    cli_plugins = lago.plugins.load_plugins(
        lago.plugins.PLUGIN_ENTRY_POINTS['cli']
    )
    out_plugins = lago.plugins.load_plugins(
        lago.plugins.PLUGIN_ENTRY_POINTS['out']
    )
    parser = create_parser(
        cli_plugins=cli_plugins,
        out_plugins=out_plugins,
    )
    args = parser.parse_args()
    config.update_args(args)

    logging.basicConfig(level=logging.DEBUG)
    logging.root.handlers = [
        log_utils.TaskHandler(
            task_tree_depth=args.logdepth,
            level=getattr(logging, args.loglevel.upper()),
            dump_level=logging.ERROR,
            formatter=log_utils.ColorFormatter(fmt='%(msg)s', )
        )
    ]

    logging.captureWarnings(True)
    if args.ignore_warnings:
        logging.getLogger('py.warnings').setLevel(logging.ERROR)
    else:
        warnings.formatwarning = lambda message, *args, **kwargs: message

    args.out_format = out_plugins[args.out_format]
    if args.prefix_path:
        warnings.warn(
            'The option --prefix-path is going to be deprecated, use '
            '--workdir and --prefix instead',
            DeprecationWarning,
        )

    try:
        cli_plugins[args.verb].do_run(args)
    except utils.LagoException as e:
        LOGGER.error(e.message)
        LOGGER.debug(e, exc_info=True)
        sys.exit(2)
    except Exception:
        LOGGER.exception('Error occured, aborting')
        sys.exit(1)


if __name__ == '__main__':
    main()
