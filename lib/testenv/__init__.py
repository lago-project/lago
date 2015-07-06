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
import json
import logging
import os
import shutil
import uuid

import config
import paths
import subnet_lease
import utils
import virt

__all__ = ['config', 'paths', 'utils', 'virt']


def _create_ip(subnet, index):
    return '.'.join(subnet.split('.')[:3] + [str(index)])


def _ip_in_subnet(subnet, ip):
    return (
        _create_ip(subnet, 1) == _create_ip(ip, 1)
        or
        '0.0.0.1' == _create_ip(ip, 1)
    )


class Prefix(object):
    def __init__(self, prefix):
        self._prefix = prefix
        self._paths = self._create_paths()
        self._virt_env = None
        self._metadata = None

    def _create_paths(self):
        return paths.Paths(self._prefix)

    def _get_metadata(self):
        if self._metadata is None:
            try:
                with open(self.paths.metadata()) as f:
                    self._metadata = json.load(f)
            except IOError:
                self._metadata = {}
        return self._metadata

    def _save_metadata(self):
        with open(self.paths.metadata(), 'w') as f:
            utils.json_dump(self._get_metadata(), f)

    def save(self):
        self._save_metadata()
        self.virt_env.save()

    @property
    def paths(self):
        return self._paths

    def _create_ssh_keys(self):
        ret, _, _ = utils.run_command(
            [
                'ssh-keygen',
                '-t', 'rsa',
                '-N', '',
                '-f', self.paths.ssh_id_rsa(),
            ]
        )
        if ret != 0:
            raise RuntimeError(
                'Failed to crate ssh keys at %s',
                self.paths.ssh_id_rsa(),
            )

    def initialize(self):
        prefix = self.paths.prefix()
        with utils.RollbackContext() as rollback:
            try:
                os.mkdir(prefix)
            except OSError:
                raise RuntimeError('Could not create prefix at %s' % prefix)
            rollback.prependDefer(shutil.rmtree, prefix)

            with open(self.paths.uuid(), 'w') as f:
                f.write(uuid.uuid1().hex)
            self._create_ssh_keys()

            rollback.clear()

    def cleanup(self):
        self.stop()

        # Remove uuid to drop all locks
        os.unlink(self.paths.uuid())

    def _config_net_topology(self, conf):
        all_nics = [
            (nic, dom_name)
            for dom_name, dom in conf['domains'].items()
            for nic in dom['nics']
        ]
        nics_by_net = {}
        for nic, dom in all_nics:
            nics_by_net.setdefault(
                nic['net'],
                []
            ).append((nic, dom))

        with utils.RollbackContext() as rollback:
            for net_name, net_spec in conf.get('nets', {}).items():
                net_spec['name'] = net_name

                if net_spec.setdefault('type', 'nat') == 'bridge':
                    continue

                try:
                    subnet = net_spec['gw']
                    if subnet_lease.is_leasable_subnet(subnet):
                        raise RuntimeError(
                            '%s subnet can only be dynamically allocated' % (
                                subnet,
                            )
                        )
                except KeyError:
                    subnet = subnet_lease.acquire(self.paths.uuid())
                    rollback.prependDefer(subnet_lease.release, subnet)
                    net_spec['gw'] = subnet

                allocated_ips = set([1])

                # Check all allocated IPs
                for nic, dom in nics_by_net[net_name]:
                    if 'ip' not in nic:
                        continue

                    if not _ip_in_subnet(subnet, nic['ip']):
                        raise RuntimeError(
                            "%s:nic%d's IP [%s] is outside the subnet [%s]",
                            dom,
                            dom['nics'].index(nic),
                            nic['ip'],
                            subnet,
                        )

                    index = int(nic['ip'].split('.'))[3]
                    allocated_ips.add(index)
                    nic['ip'] = _create_ip(subnet, index)

                # Allocate IPs for domains without assigned IPs
                for nic, _ in nics_by_net[net_name]:
                    if 'ip' in nic:
                        continue

                    next_vacancy = set(
                        set(range(1, 255)) ^ allocated_ips
                    ).pop()
                    allocated_ips.add(next_vacancy)
                    nic['ip'] = _create_ip(subnet, next_vacancy)

                logging.info('Creating bridge...')
                if 'mapping' not in net_spec:
                    net_spec['mapping'] = {}
                net_spec['mapping'].update(
                    {
                        dom: nic['ip']
                        for nic, dom in nics_by_net[net_name]
                    },
                )
            rollback.clear()

    def _create_disk(
        self,
        name,
        spec,
        template_repo=None,
        template_store=None,
    ):
        logging.debug("Creating disk for '%s': %s", name, spec)
        disk_metadata = {}

        disk_filename = '%s_%s.%s' % (name, spec['name'], spec['format'])
        disk_path = self.paths.images(disk_filename)
        if spec['type'] == 'template':
            if template_store is None or template_repo is None:
                raise RuntimeError('No templates directory provided')

            template = template_repo.get_by_name(spec['template_name'])
            template_version = template.get_version(
                spec.get('template_version', None)
            )

            if template_version not in template_store:
                template_store.download(template_version)
            template_store.mark_used(template_version, self.paths.uuid())

            disk_metadata.update(
                template_store.get_stored_metadata(
                    template_version,
                ),
            )

            base = template_store.get_path(template_version)
            qemu_img_cmd = ['qemu-img', 'create', '-f', 'qcow2',
                            '-b', base, disk_path]

            try:
                template_hash = template_store.get_stored_hash(
                    template_version
                )
            except:
                template_hash = '<unversioned>'

            logging.info(
                'Creating disk %s:%s from template image %s, versioned as %s',
                name,
                spec['name'],
                spec['template_name'],
                template_hash,
            )
        elif spec['type'] == 'empty':
            qemu_img_cmd = ['qemu-img', 'create', '-f', spec['format'],
                            disk_path, spec['size']]
        elif spec['type'] == 'file':
            # If we're using raw file, just return it's path
            return spec['path'], disk_metadata
        else:
            raise RuntimeError('Unknown drive spec %s' % str(spec))

        if os.path.exists(disk_path):
            os.unlink(disk_path)

        logging.debug('Running command: %s', ' '.join(qemu_img_cmd))
        ret, _, _ = utils.run_command(qemu_img_cmd)
        if ret != 0:
            raise RuntimeError(
                'Failed to create image, qemu-img returned %d' % ret,
            )
        # To avoid losing access to the file
        os.chmod(disk_path, 0666)

        logging.info('Successfully created disk at %s', disk_path)
        return disk_path, disk_metadata

    def virt_conf(
        self,
        conf,
        template_repo=None,
        template_store=None,
    ):
        with utils.RollbackContext() as rollback:
            if not os.path.exists(self.paths.images()):
                os.mkdir(self.paths.images())
                rollback.prependDefer(os.unlink, self.paths.images())

            if not os.path.exists(self.paths.virt()):
                os.mkdir(self.paths.virt())
                rollback.prependDefer(os.unlink, self.paths.virt())

            self._config_net_topology(conf)

            for name, spec in conf['domains'].items():
                new_disks = []
                spec['name'] = name
                for disk in spec['disks']:
                    path, metadata = self._create_disk(
                        name,
                        disk,
                        template_repo,
                        template_store,
                    )
                    new_disks.append(
                        {
                            'path': path,
                            'dev': disk['dev'],
                            'format': disk['format'],
                            'metadata': metadata,
                        },
                    )
                conf['domains'][name]['disks'] = new_disks

            env = virt.VirtEnv(self, conf['domains'], conf['nets'])
            env.save()
            env.bootstrap()
            rollback.clear()

    def start(self):
        self.virt_env.start()

    def stop(self):
        self.virt_env.stop()

    def create_snapshots(self, name):
        self.virt_env.create_snapshots(name)

    def revert_snapshots(self, name):
        self.virt_env.revert_snapshots(name)

    def _create_virt_env(self):
        return virt.VirtEnv.from_prefix(self)

    @property
    def virt_env(self):
        if self._virt_env is None:
            self._virt_env = self._create_virt_env()
        return self._virt_env
