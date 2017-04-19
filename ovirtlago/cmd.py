#!/usr/bin/env python2
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
import logging
import os
import sys
import warnings

import lago
from lago.config import config as lago_config
from lago.log_utils import LogTask
from lago.plugins.cli import CLIPlugin, cli_plugin, cli_plugin_add_argument
from lago.utils import in_prefix, with_logging
from ovirtlago.prefix import OvirtPrefix, OvirtWorkdir

LOGGER = logging.getLogger('ovirt-cli')
in_ovirt_prefix = in_prefix(
    prefix_class=OvirtPrefix,
    workdir_class=OvirtWorkdir,
)
# TODO: Remove this, and properly complain on unset config values
DISTS = ['el6', 'el7', 'fc20']


@cli_plugin(
    help=(
        'Create snapshots for all deployed resources. This command puts the '
        'storages, domains and hosts into maintenance before taking snapshot.'
    )
)
@cli_plugin_add_argument(
    'snapshot_name',
    help='Name of the snapshot to create',
    metavar='SNAPSHOT_NAME',
)
@cli_plugin_add_argument(
    '--no-restore',
    help=(
        'Do not bring system in to previous state (active storage '
        'domains/hosts/services)'
    ),
    action='store_false',
    dest='restore',
)
@in_ovirt_prefix
@with_logging
def do_ovirt_snapshot(prefix, snapshot_name, no_restore, **kwargs):
    prefix.create_snapshots(snapshot_name, no_restore)


@cli_plugin(
    help=(
        'Revert to a previously created snapshot.\n'
        'This command activates storage domains and hosts after booting up.'
    )
)
@cli_plugin_add_argument(
    'snapshot_name',
    help='Name of the snapshot to create',
    metavar='SNAPSHOT_NAME',
)
@in_ovirt_prefix
@with_logging
def do_ovirt_revert(prefix, snapshot_name, **kwargs):
    prefix.revert_snapshots(snapshot_name)


@cli_plugin(help='Run unit tests from a specified file')
@cli_plugin_add_argument(
    'test_file',
    help='Path to tests file to run',
    metavar='TEST_FILE',
)
@in_ovirt_prefix
@with_logging
def do_ovirt_runtest(prefix, test_file, **kwargs):
    if not os.path.exists(test_file):
        raise RuntimeError('Test file not found')
    if not prefix.run_test(test_file):
        raise RuntimeError('Some tests failed')


@cli_plugin(
    help=(
        'Create a local rpm repository with rpms provided by external '
        'repository and rpms build from engine/vdsm sources if provided.'
    )
)
@cli_plugin_add_argument(
    '--rpm-repo',
    help='Path to local rpm repository',
    type=os.path.abspath,
)
@cli_plugin_add_argument(
    '--reposync-yum-config',
    help=('Path to configuration to use when updating local rpm repository'),
    type=os.path.abspath,
    default=None,
)
@cli_plugin_add_argument(
    '--skip-sync',
    help='Do not sync repos',
    action='store_true',
)
@cli_plugin_add_argument(
    '--custom-source',
    help=(
        'Add an extra rpm source to the repo (will have priority over the '
        'repos), allows any source string allowed by repoman'
    ),
    dest='custom_sources',
    action='append',
)
@cli_plugin_add_argument(
    '--repoman-config',
    help=(
        'Custom repoman configuration file. If not passed defaults will be '
        'used. Note that \'store.RPMStore.rpm_dir\' is not configurable.'
    ),
    dest='repoman_config',
    action='store',
    default=None,
)
@in_ovirt_prefix
@with_logging
def do_ovirt_reposetup(
    prefix, rpm_repo, reposync_yum_config, repoman_config, skip_sync,
    custom_sources, **kwargs
):

    if rpm_repo is None:
        rpm_repo = lago_config['reposync_dir']

    prefix.prepare_repo(
        rpm_repo=rpm_repo,
        reposync_yum_config=reposync_yum_config,
        skip_sync=skip_sync,
        custom_sources=custom_sources,
        repoman_config=repoman_config,
    )


@cli_plugin(help='Run scripts that install necessary RPMs and configuration')
@in_ovirt_prefix
@with_logging
def do_deploy(prefix, **kwargs):
    prefix.deploy()


@cli_plugin(help='Run engine-setup command on the engine machine')
@cli_plugin_add_argument(
    '--config',
    help='Path to answer file',
    type=os.path.abspath,
)
@in_ovirt_prefix
@with_logging
def do_ovirt_engine_setup(prefix, config, **kwargs):
    prefix.virt_env.engine_vm().engine_setup(config)


@cli_plugin(help='Start all hosts that are in maintenance')
@in_ovirt_prefix
@with_logging
def do_ovirt_start_hosts(prefix, **kwargs):
    prefix.virt_env.engine_vm().start_all_hosts()


@cli_plugin(help='Stop all hosts that are up')
@in_ovirt_prefix
@with_logging
def do_ovirt_stop_hosts(prefix, **kwargs):
    prefix.virt_env.engine_vm().stop_all_hosts()


@cli_plugin(help='Stop all VMs that are up')
@in_ovirt_prefix
@with_logging
def do_ovirt_stop_vms(prefix, **kwargs):
    prefix.virt_env.engine_vm().stop_all_vms()


@cli_plugin(help='Start all VMs that are down')
@in_ovirt_prefix
@with_logging
def do_ovirt_start_vms(prefix, **kwargs):
    prefix.virt_env.engine_vm().start_all_vms()


@cli_plugin(help='Print oVirt setup status')
@in_ovirt_prefix
@with_logging
def do_ovirt_status(prefix, **kwargs):
    prefix.virt_env.engine_vm().status()


@cli_plugin(
    help=(
        'Start oVirt environment: Start Engine and Host VMs, then '
        'put Hosts in activate mode.'
    )
)
@cli_plugin_add_argument(
    '--with-vms',
    help=('Also Start VMs connected to to the Engine.'),
    dest='with_vms',
    action='store_true',
)
@in_ovirt_prefix
@with_logging
def do_ovirt_start(prefix, with_vms, **kwargs):
    with LogTask('Starting oVirt environment'):
        prefix.start()
        with LogTask('Waiting for ovirt-engine status'):
            prefix.virt_env.assert_engine_alive()
        with LogTask('Waiting for vdsmd status'):
            prefix.virt_env.assert_vdsm_alive()
        with LogTask('Activating Engine Hosts'):
            prefix.virt_env.engine_vm().start_all_hosts()
        if with_vms:
            with LogTask('Waiting for Storage domains to be in active mode'):
                prefix.virt_env.engine_vm().check_sds_status()
            with LogTask('Starting Engine VMs'):
                prefix.virt_env.engine_vm().start_all_vms()


@cli_plugin(
    help=(
        'Stop all Engine VMs, put all hosts in maintenance and turn off '
        ' Lago VMs.'
    )
)
@in_ovirt_prefix
@with_logging
def do_ovirt_stop(prefix, **kwargs):
    with LogTask('Stopping oVirt environment'):
        with LogTask('Stopping Engine VMs'):
            prefix.virt_env.engine_vm().stop_all_vms()
        with LogTask('Putting hosts in maintenance mode'):
            prefix.virt_env.engine_vm().stop_all_hosts()
        with LogTask('Shutdown Lago VMs'):
            prefix.shutdown()


@cli_plugin(
    help=(
        'Collect logs from VMs, list of collected logs '
        'can be specified in the init file, under '
        'artifacts parameter '
    )
)
@cli_plugin_add_argument(
    '--output',
    help='Path to place all the extracted at',
    required=True,
    type=os.path.abspath,
)
@cli_plugin_add_argument(
    '--no-skip',
    help='do not skip missing paths',
    action='store_true',
)
@in_ovirt_prefix
@with_logging
def do_ovirt_collect(prefix, output, no_skip, **kwargs):
    warnings.warn(
        (
            '\'lago ovirt collect\' is deprecated, redirecting '
            'to \'lago collect\''
        )
    )
    lago.cmd.do_collect(prefix=prefix, output=output, no_skip=no_skip)


@cli_plugin(help='Start the repo server and do nothing')
@in_ovirt_prefix
@with_logging
def do_ovirt_serve(prefix, **kwargs):
    prefix.serve()


def _populate_parser(cli_plugins, parser):
    verbs_parser = parser.add_subparsers(
        dest='ovirtverb',
        metavar='VERB',
    )
    for cli_plugin_name, plugin in cli_plugins.items():
        plugin_parser = verbs_parser.add_parser(
            cli_plugin_name, **plugin.init_args
        )
        plugin.populate_parser(plugin_parser)

    return parser


class OvirtCLI(CLIPlugin):
    init_args = {
        'help': 'oVirt related actions',
    }

    def populate_parser(self, parser):
        self.cli_plugins = lago.plugins.load_plugins('lago.plugins.ovirt.cli')
        _populate_parser(self.cli_plugins, parser)
        return parser

    def do_run(self, args):
        try:
            self.cli_plugins[args.ovirtverb].do_run(args)

        except Exception:
            logging.exception('Error occured, aborting')
            sys.exit(1)
