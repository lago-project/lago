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
import ConfigParser
import functools
import logging
import os
import time

import nose.core
import nose.config
from ovirtsdk.infrastructure.errors import (RequestError, ConnectionError)
import lago
from lago import log_utils
from lago.prefix import DefaultPrefix
from lago.workdir import Workdir

from . import (paths, testlib, virt, reposetup, )

# TODO: put it into some config
PROJECTS_LIST = ['vdsm', 'ovirt-engine', 'vdsm-jsonrpc-java', 'ioprocess', ]
LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


def _activate_storage_domains(api, sds):
    if not sds:
        LOGGER.info('No storages to activate')
        return

    for sd in sds:
        if sd.status.get_state() != 'active':
            sd.activate()
            LOGGER.info('Started activation of storage domain %s', sd.name)
        else:
            LOGGER.info('Storage domain %s already active', sd.name)

    with LogTask('Waiting for the domains to become active'):
        for sd in sds:
            dc = api.datacenters.get(id=sd.get_data_center().get_id(), )
            with LogTask(
                'Waiting for storage domain %s to become active' % sd.name,
                level='debug'
            ):
                testlib.assert_true_within_long(
                    lambda: (
                        dc.storagedomains.get(sd.name).status.state == 'active'
                    )
                )


def _deactivate_storage_domains(api, sds):
    if not sds:
        LOGGER.info('No storages to deactivate')
        return

    for sd in sds:
        if sd.status.get_state() != 'maintenance':
            sd.deactivate()
            LOGGER.info('Started deactivation of storage domain %s', sd.name)
        else:
            LOGGER.info('Storage domain %s already inactive', sd.name)

    with LogTask('Waiting for the domains to get into maintenance'):
        for sd in sds:
            dc = api.datacenters.get(id=sd.get_data_center().get_id())
            with LogTask(
                'Waiting for storage domain %s to become inactive' % sd.name,
                level='debug'
            ):
                testlib.assert_true_within_long(
                    lambda: (
                        dc.storagedomains.get(sd.name).status.state ==
                        'maintenance'
                    ),
                )


@log_task('Deactivating all storage domains')
def _deactivate_all_storage_domains(api):
    for dc in api.datacenters.list():
        with LogTask('Deactivating domains for datacenter %s' % dc.name):
            sds = dc.storagedomains.list()
            with LogTask('Deactivating non-master storage domains'):
                _deactivate_storage_domains(
                    api,
                    [sd for sd in sds if not sd.master],
                )
            with LogTask('Deactivating master storage domains'):
                _deactivate_storage_domains(
                    api,
                    [sd for sd in sds if sd.master],
                )


def _deactivate_all_hosts(api):
    hosts = api.hosts.list()

    while hosts:
        host = hosts.pop()
        try:
            host.deactivate()
            LOGGER.info('Sent host %s to maintenance', host.name)
        except RequestError:
            LOGGER.exception('Failed to maintenance host %s', host.name)
            hosts.insert(0, host)

    for host in api.hosts.list():
        with LogTask(
            'Wait for %s to go into maintenance' % host.name,
            level='debug',
        ):
            testlib.assert_true_within_short(
                lambda: api.hosts.get(host.name).status.state == 'maintenance',
            )


def _activate_all_hosts(api):
    names = [host.name for host in api.hosts.list()]

    for name in names:
        try:
            api.hosts.get(name).activate()
        except RequestError:
            pass

    for name in names:
        testlib.assert_true_within_short(
            lambda: api.hosts.get(name).status.state == 'up',
        )


@log_task('Activating all storage domains')
def _activate_all_storage_domains(api):
    for dc in api.datacenters.list():
        with LogTask('Activating domains for datacenter %s' % dc.name):
            sds = dc.storagedomains.list()
            with LogTask('Activating master storage domains'):
                _activate_storage_domains(
                    api,
                    [sd for sd in sds if sd.master],
                )
            with LogTask('Activating non-master storage domains'):
                _activate_storage_domains(
                    api,
                    [sd for sd in sds if not sd.master],
                )


class OvirtPrefix(DefaultPrefix):
    VIRT_ENV_CLASS = virt.OvirtVirtEnv

    def __init__(self, *args, **kwargs):
        super(OvirtPrefix, self).__init__(*args, **kwargs)
        self.paths = paths.OvirtPaths(self._prefix)

    def create_snapshots(self, name, restore=True):
        with lago.utils.RollbackContext() as rollback, \
                LogTask('Create snapshots'):
            engine = self.virt_env.engine_vm()

            self._deactivate()
            rollback.prependDefer(self._activate)

            # stop engine:
            engine.service('ovirt-engine').stop()
            rollback.prependDefer(engine.get_api)
            rollback.prependDefer(engine.service('ovirt-engine').start)

            # stop VDSMs:
            def stop_host(host):
                host.service('vdsmd').stop()
                rollback.prependDefer(host.service('vdsmd').start)

                host.service('supervdsmd').stop()
                rollback.prependDefer(host.service('supervdsmd').start)

            lago.utils.invoke_in_parallel(stop_host, self.virt_env.host_vms())

            super(OvirtPrefix, self).create_snapshots(name)

            if not restore:
                rollback.clear()

    def revert_snapshots(self, name):
        super(OvirtPrefix, self).revert_snapshots(name)
        self._activate()

    def _create_rpm_repository(
        self,
        dists,
        repos_path,
        repo_names,
        custom_sources=None,
        projects_list=None,
    ):

        if not projects_list:
            projects_list = PROJECTS_LIST

        custom_sources = custom_sources or []

        rpm_dirs = []
        for dist in dists:
            project_roots = [
                self.paths.build_dir(project_name)
                for project_name in projects_list
            ]

            rpm_dirs.extend(
                [
                    os.path.join(folder, dist) + ':only-missing'
                    for folder in project_roots if os.path.exists(folder)
                ]
            )

            rpm_dirs.extend(
                [
                    os.path.join(repos_path, name) + ':only-missing'
                    for name in repo_names if name.endswith(dist)
                ],
            )

        reposetup.merge(
            output_dir=self.paths.internal_repo(),
            sources=custom_sources + rpm_dirs,
        )

    @log_task('Create prefix internal repo')
    def prepare_repo(
        self,
        rpm_repo=None,
        reposync_yum_config=None,
        skip_sync=False,
        custom_sources=None
    ):
        custom_sources = custom_sources or []
        # Detect distros from template metadata
        engine_dists = [self.virt_env.engine_vm().distro()] \
            if self.virt_env.engine_vm() else []
        vdsm_dists = list(
            set(
                [
                    host.distro() for host in self.virt_env.host_vms()
                ]
            )
        )
        all_dists = list(set(engine_dists + vdsm_dists))

        repos = []

        if rpm_repo and reposync_yum_config:
            parser = ConfigParser.SafeConfigParser()
            with open(reposync_yum_config) as repo_conf_fd:
                parser.readfp(repo_conf_fd)

            repos = [
                repo
                for repo in parser.sections()
                if repo.split('-')[-1] in all_dists
            ]

            if not skip_sync:
                with LogTask(
                    'Syncing remote repos locally (this might take some time)'
                ):
                    reposetup.sync_rpm_repository(
                        rpm_repo,
                        reposync_yum_config,
                        repos,
                    )

        self._create_rpm_repository(
            dists=all_dists,
            repos_path=rpm_repo,
            repo_names=repos,
            custom_sources=custom_sources,
        )
        self.save()

    @reposetup.with_repo_server
    def run_test(self, path):

        with LogTask('Run test: %s' % os.path.basename(path)):
            env = os.environ.copy()
            env['LAGO_PREFIX'] = self.paths.prefix
            results_path = os.path.abspath(
                os.path.join(
                    self.paths.prefix,
                    'nosetests-%s.xml' % os.path.basename(path),
                )
            )
            extra_args = [
                '--with-xunit',
                '--xunit-file=%s' % results_path,
                '--with-tasklog-plugin',
                '--with-log-collector-plugin',
            ]

            class DummyStream(object):
                def write(self, *args):
                    pass

                def writeln(self, *args):
                    pass

                def flush(self):
                    pass

            config = nose.config.Config(
                verbosity=3,
                env=env,
                plugins=nose.core.DefaultPluginManager(),
                stream=DummyStream(),
                stopOnError=True,
            )
            addplugins = [
                testlib.TaskLogNosePlugin(),
                testlib.LogCollectorPlugin(self),
            ]
            result = nose.core.run(
                argv=['testrunner', path] + extra_args,
                config=config,
                addplugins=addplugins,
            )

            LOGGER.info('Results located at %s' % results_path)

            return result

    @log_task('Deploy oVirt environment')
    @reposetup.with_repo_server
    def deploy(self):
        return super(OvirtPrefix, self).deploy()

    @reposetup.with_repo_server
    def serve(self):
        try:
            while True:
                time.sleep(0.1)
        except:
            pass

    def _create_virt_env(self):
        return virt.OvirtVirtEnv.from_prefix(self)

    def _activate(self):
        with LogTask('Wait for ssh connectivity'):
            for vm in self.virt_env.get_vms().values():
                vm.wait_for_ssh()

        with LogTask('Wait for engine to go online'):
            testlib.assert_true_within_long(
                lambda: self.virt_env.engine_vm().get_api() or True,
                allowed_exceptions=[RequestError, ConnectionError],
            )

        api = self.virt_env.engine_vm().get_api()
        with LogTask('Activate hosts'):
            _activate_all_hosts(api)
        with LogTask('Activate storage domains'):
            _activate_all_storage_domains(api)

    def _deactivate(self):
        api = self.virt_env.engine_vm().get_api()

        with LogTask('Deactivate storage domains'):
            _deactivate_all_storage_domains(api)

        with LogTask('Deactivate hosts'):
            _deactivate_all_hosts(api)

    def start(self):
        super(OvirtPrefix, self).start()
        with LogTask('Activate'):
            self._activate()

    def stop(self):
        with LogTask('Deactivate'):
            self._deactivate()

        super(OvirtPrefix, self).stop()


class OvirtWorkdir(Workdir):
    def __init__(self, *args, **kwargs):
        super(OvirtWorkdir, self).__init__(*args, **kwargs)
        self.prefix_class = OvirtPrefix
