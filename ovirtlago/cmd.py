#!/usr/bin/python
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
import ovirtlago
from lago.plugins.cli import (CLIPlugin, cli_plugin, cli_plugin_add_argument)
from lago.utils import (in_prefix, with_logging)

LOGGER = logging.getLogger('ovirt-cli')
in_ovirt_prefix = in_prefix(
    prefix_class=ovirtlago.OvirtPrefix,
    workdir_class=ovirtlago.OvirtWorkdir,
)
# TODO: Remove this, and properly complain on unset config values
CONF_DEFAULTS = {
    'reposync_dir': '/var/lib/lago/reposync',
    'reposync_config': (
        '/usr/share/ovirtlago/config/repos/'
        'ovirt-master-snapshot-external.repo'
    ),
}
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
)
@cli_plugin_add_argument(
    '--skip-sync',
    help='Do not sync repos',
    action='store_true',
)
@cli_plugin_add_argument(
    '--engine-dir',
    help=('Deprecated, left here for backwards compatibility'),
)
@cli_plugin_add_argument(
    '--vdsm-dir',
    help=('Deprecated, left here for backwards compatibility'),
)
@cli_plugin_add_argument(
    '--ioprocess-dir',
    help=('Deprecated, left here for backwards compatibility'),
)
@in_ovirt_prefix
@with_logging
def do_ovirt_reposetup(
    prefix, rpm_repo, reposync_yum_config, skip_sync, **kwargs
):

    if kwargs['engine_dir']:
        warnings.warn('Deprecated option --engine-dir ignored')
    if kwargs['vdsm_dir']:
        warnings.warn('Deprecated option --vdsm-dir ignored')
    if kwargs['ioprocess_dir']:
        warnings.warn('Deprecated option --ioprocess-dir ignored')

    rpm_repo = (
        rpm_repo
        or lago.config.get('reposync_dir', CONF_DEFAULTS['reposync_dir'])
    )

    reposync_config = (
        reposync_yum_config or lago.config.get(
            'reposync_config',
            CONF_DEFAULTS['reposync_config'],
        )
    )

    prefix.prepare_repo(
        rpm_repo=rpm_repo,
        reposync_yum_config=reposync_config,
        skip_sync=skip_sync,
    )


@cli_plugin(help='Run scripts that install necessary RPMs and configuration')
@in_ovirt_prefix
@with_logging
def do_deploy(prefix, **kwargs):
    prefix.deploy()


@cli_plugin(
    help='Start all resources and activate all storage domains and hosts.'
)
@in_ovirt_prefix
@with_logging
def do_ovirt_start(prefix, **kwargs):
    prefix.start()


@cli_plugin(
    help='Maintenance all storage domains and hosts, and stop all resources',
)
@in_ovirt_prefix
@with_logging
def do_ovirt_stop(prefix, **kwargs):
    prefix.stop()


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


@cli_plugin(help='Collect logs from running VMs')
@cli_plugin_add_argument(
    '--output',
    help='Path to place all the extracted at',
    required=True,
    type=os.path.abspath,
)
@in_ovirt_prefix
@with_logging
def do_ovirt_collect(prefix, output, **kwargs):
    prefix.collect_artifacts(output)


@cli_plugin(help='Start the repo server and do nothing')
@in_ovirt_prefix
@with_logging
def do_ovirt_serve(prefix, **kwargs):
    prefix.serve()


def _populate_parser(cli_plugins, parser):
    verbs_parser = parser.add_subparsers(dest='ovirtverb', metavar='VERB', )
    for cli_plugin_name, plugin in cli_plugins.items():
        plugin_parser = verbs_parser.add_parser(
            cli_plugin_name, **plugin.init_args
        )
        plugin.populate_parser(plugin_parser)

    return parser


class OvirtCLI(CLIPlugin):
    init_args = {'help': 'oVirt related actions', }

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
