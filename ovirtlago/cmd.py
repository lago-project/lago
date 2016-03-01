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
import collections
import functools
import logging
import os
import sys

import lago
import ovirtlago
from lago.plugins.cli import CLIPlugin

LOGGER = logging.getLogger('ovirt-cli')

# TODO: Remove this, and properly complain on unset config values
CONF_DEFAULTS = {
    'reposync_dir': '/var/lib/lago/reposync',
    'reposync_config': (
        '/usr/share/ovirtlago/config/repos/'
        'ovirt-master-snapshot-external.repo'
    ),
}
DISTS = ['el6', 'el7', 'fc20']


def in_prefix(func):
    @functools.wraps(func)
    def wrapper(args):
        prefix_path = getattr(args, 'prefix_path', 'auto')
        if prefix_path == 'auto':
            prefix_path = lago.prefix.resolve_prefix_path()

        prefix = ovirtlago.OvirtPrefix(prefix_path)
        return func(prefix, args)

    return wrapper


def with_logging(func):
    @functools.wraps(func)
    def wrapper(prefix, args):
        lago.log_utils.setup_prefix_logging(prefix.paths.logs())
        return func(prefix, args)

    return wrapper


@in_prefix
@with_logging
def do_ovirt_snapshot(prefix, args):
    prefix.create_snapshots(args.snapshot_name, args.restore)


@in_prefix
@with_logging
def do_ovirt_revert(prefix, args):
    prefix.revert_snapshots(args.snapshot_name)


@in_prefix
@with_logging
def do_ovirt_runtest(prefix, args):
    if not os.path.exists(args.test_file):
        raise RuntimeError('Test file not found')
    if not prefix.run_test(args.test_file):
        raise RuntimeError('Some tests failed')


@in_prefix
@with_logging
def do_ovirt_reposetup(prefix, args):
    rpm_repo = (
        args.rpm_repo
        or lago.config.get('reposync_dir', CONF_DEFAULTS['reposync_dir'])
    )

    reposync_config = (
        args.reposync_yum_config or lago.config.get(
            'reposync_config',
            CONF_DEFAULTS['reposync_config'],
        )
    )

    prefix.prepare_repo(
        rpm_repo=rpm_repo,
        reposync_yum_config=reposync_config,
        skip_sync=args.skip_sync,
        engine_dir=args.engine_dir,
        engine_build_gwt=args.engine_with_gwt,
        ioprocess_dir=args.ioprocess_dir,
        vdsm_dir=args.vdsm_dir,
        vdsm_jsonrpc_java_dir=args.vdsm_jsonrpc_java_dir,
    )


@in_prefix
@with_logging
def do_deploy(prefix, args):
    prefix.deploy()


@in_prefix
@with_logging
def do_ovirt_start(prefix, args):
    prefix.start()


@in_prefix
@with_logging
def do_ovirt_stop(prefix, args):
    prefix.stop()


@in_prefix
@with_logging
def do_ovirt_engine_setup(prefix, args):
    prefix.virt_env.engine_vm().engine_setup(args.config)


@in_prefix
@with_logging
def do_ovirt_collect(prefix, args):
    prefix.collect_artifacts(args.output)


@in_prefix
@with_logging
def do_ovirt_serve(prefix, args):
    prefix.serve()


class Verbs:
    OVIRT_DEPLOY = 'deploy'
    OVIRT_REPOSETUP = 'reposetup'
    OVIRT_RUNTEST = 'runtest'
    OVIRT_SNAPSHOT = 'snapshot'
    OVIRT_REVERT = 'revert'
    OVIRT_START = 'start'
    OVIRT_STOP = 'stop'
    OVIRT_ENGINE_SETUP = 'engine-setup'
    OVIRT_COLLECT = 'collect'
    OVIRT_SERVE = 'serve'


ARGUMENTS = collections.OrderedDict()
ARGUMENTS[Verbs.OVIRT_DEPLOY] = (
    'Run scripts that install necessary RPMs and configuration',
    (),
    do_deploy,
)
ARGUMENTS[Verbs.OVIRT_REPOSETUP] = (
    (
        'Create a local rpm repository with rpms provided by external '
        'repository and rpms build from engine/vdsm sources if provided.'
    ),
    (
        (
            '--rpm-repo',
            {
                'help': 'Path to local rpm repository',
                'type': os.path.abspath,
            }
        ),
        (
            '--reposync-yum-config',
            {
                'help': (
                    'Path to configuration to use when updating local rpm '
                    'repository'
                ),
                'type': os.path.abspath,
            },
        ),
        (
            '--skip-sync',
            {
                'help': 'Do not sync repos',
                'action': 'store_true',
            },
        ),
        (
            '--engine-dir',
            {
                'help': 'Path to oVirt engine source'
            },
        ),
        (
            '--engine-with-gwt',
            {
                'help': 'Build GWT when build engine rpms',
                'action': 'store_true',
            },
        ),
        (
            '--ioprocess-dir',
            {
                'help': 'Path to ioprocess source',
            },
        ),
        (
            '--vdsm-dir',
            {
                'help': 'Path to VDSM source'
            },
        ),
        (
            '--vdsm-jsonrpc-java-dir',
            {
                'help': 'Path to vdsm-jsonrpc-java source'
            },
        ),
    ),
    do_ovirt_reposetup,
)
ARGUMENTS[Verbs.OVIRT_RUNTEST] = (
    'Run unit tests from a specified file',
    (
        (
            'test_file',
            {
                'help': 'Path to tests file to run',
                'metavar': 'TEST_FILE',
            },
        ),
    ),
    do_ovirt_runtest,
)
ARGUMENTS[Verbs.OVIRT_SNAPSHOT] = (
    (
        'Create snapshots for all deployed resources.\n'
        'This command maintenances storage domains and hosts before '
        'taking snapshot.'
    ),
    (
        (
            'snapshot_name',
            {
                'help': 'Name of the snapshot to create',
                'metavar': 'SNAPSHOT_NAME',
            },
        ),
        (
            '--no-restore',
            {
                'help': (
                    'Do not bring system in to previous state '
                    '(active storage domains/hosts/services)'
                ),
                'action': 'store_false',
                'dest': 'restore',
            },
        ),
    ),
    do_ovirt_snapshot,
)
ARGUMENTS[Verbs.OVIRT_REVERT] = (
    (
        'Revert to a previously created snapshot.\n'
        'This command activates storage domains and hosts after booting up.'
    ),
    (
        (
            'snapshot_name',
            {
                'help': 'Name of the snapshot to create',
                'metavar': 'SNAPSHOT_NAME',
            },
        ),
    ),
    do_ovirt_revert,
)
ARGUMENTS[Verbs.OVIRT_START] = (
    'Start all resources and activate all storage domains and hosts.',
    (),
    do_ovirt_start,
)
ARGUMENTS[Verbs.OVIRT_STOP] = (
    'Maintenance all storage domains and hosts, and stop all resources',
    (),
    do_ovirt_stop,
)
ARGUMENTS[Verbs.OVIRT_ENGINE_SETUP] = (
    'Run engine-setup command on the engine machine',
    (
        (
            '--config',
            {
                'help': 'Path to answer file',
                'type': os.path.abspath,
            },
        ),
    ),
    do_ovirt_engine_setup,
)
ARGUMENTS[Verbs.OVIRT_COLLECT] = (
    'Collect logs from running VMs',
    (
        (
            '--output',
            {
                'help': 'Path to place all the extracted at',
                'required': True,
                'type': os.path.abspath,
            },
        ),
    ),
    do_ovirt_collect,
)
ARGUMENTS[Verbs.OVIRT_SERVE] = (
    'Start the repo server and do nothing',
    (),
    do_ovirt_serve,
)


class OvirtCLI(CLIPlugin):
    init_args = {'help': 'oVirt related actions', }

    def populate_parser(self, parser):
        verbs = parser.add_subparsers(dest='ovirtverb', metavar='VERB')
        for verb, (desc, args, _) in ARGUMENTS.items():
            verb_parser = verbs.add_parser(verb, help=desc)
            for arg_name, arg_kw in args:
                verb_parser.add_argument(arg_name, **arg_kw)
        return parser

    def do_run(self, args):
        try:
            _, _, func = ARGUMENTS[args.ovirtverb]
            func(args)
        except Exception:
            logging.exception('Error occured, aborting')
            sys.exit(1)
