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

import functools
import logging
import os
import time
from configparser import SafeConfigParser

import nose.core
import nose.config
from lago.prefix import Prefix
from lago.workdir import Workdir
from lago import log_utils
from . import (
    paths,
    testlib,
    virt,
    reposetup,
)

# TODO: put it into some config
PROJECTS_LIST = [
    'vdsm',
    'ovirt-engine',
    'vdsm-jsonrpc-java',
    'ioprocess',
]
LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


class OvirtPrefix(Prefix):
    VIRT_ENV_CLASS = virt.OvirtVirtEnv

    def __init__(self, *args, **kwargs):
        super(OvirtPrefix, self).__init__(*args, **kwargs)
        self.paths = paths.OvirtPaths(self._prefix)

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
            set([host.distro() for host in self.virt_env.host_vms()])
        )
        all_dists = list(set(engine_dists + vdsm_dists))

        repos = []

        if rpm_repo and reposync_yum_config:
            parser = SafeConfigParser()
            with open(reposync_yum_config) as repo_conf_fd:
                parser.readfp(repo_conf_fd)

            repos = [
                repo for repo in parser.sections()
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
                stopOnError=False,
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


class OvirtWorkdir(Workdir):
    def __init__(self, *args, **kwargs):
        super(OvirtWorkdir, self).__init__(*args, **kwargs)
        self.prefix_class = OvirtPrefix
