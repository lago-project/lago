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
import copy
import json
import logging
import os
import shutil
import uuid

import paths
import subnet_lease
import utils
import virt


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

    def _init_net_specs(self, conf):
        for net_name, net_spec in conf.get('nets', {}).items():
            net_spec['name'] = net_name
            net_spec['mapping'] = {}
            net_spec.setdefault('type', 'nat')

    def _check_predefined_subnets(self, conf):
        for net_name, net_spec in conf.get('nets', {}).items():
            subnet = net_spec.get('gw')
            if subnet is None:
                continue

            if subnet_lease.is_leasable_subnet(subnet):
                raise RuntimeError(
                    '%s subnet can only be dynamically allocated' % (subnet)
                )

    def _allocate_subnets(self, conf):
        allocated_subnets = []
        try:
            for net_name, net_spec in conf.get('nets', {}).items():
                if 'gw' in net_spec or net_spec['type'] != 'nat':
                    continue
                net_spec['gw'] = subnet_lease.acquire(self.paths.uuid())
                allocated_subnets.append(net_spec['gw'])
        except:
            for subnet in allocated_subnets:
                subnet_lease.release(subnet)

        return allocated_subnets

    def _add_nic_to_mapping(self, net, dom, nic):
        dom_name = dom['name']
        idx = dom['nics'].index(nic)
        name = idx == 0 and dom_name or '%s-eth%d' % (dom_name, idx)
        net['mapping'][name] = nic['ip']

    def _register_preallocated_ips(self, conf):
        for dom_name, dom_spec in conf.get('domains', {}).items():
            for idx, nic in enumerate(dom_spec.get('nics', [])):
                if 'ip' not in nic:
                    continue

                net = conf['nets'][nic['net']]
                if subnet_lease.is_leasable_subnet(net['gw']):
                    nic['ip'] = _create_ip(
                        net['gw'],
                        int(nic['ip'].split('.')[-1])
                    )

                dom_name = dom_spec['name']
                if not _ip_in_subnet(net['gw'], nic['ip']):
                    raise RuntimeError(
                        "%s:nic%d's IP [%s] is outside the subnet [%s]",
                        dom_name,
                        dom_spec['nics'].index(nic),
                        nic['ip'],
                        net['gw'],
                    )

                if nic['ip'] in net['mapping'].values():
                    conflict_list = [
                        name for name, ip in net['mapping'].items()
                        if ip == net['ip']
                    ]
                    raise RuntimeError(
                        'IP %s was to several domains: %s %s' % (
                            nic['ip'],
                            dom_name,
                            ' '.join(conflict_list),
                        ),
                    )

                self._add_nic_to_mapping(net, dom_spec, nic)

    def _allocate_ips_to_nics(self, conf):
        for dom_name, dom_spec in conf.get('domains', {}).items():
            for idx, nic in enumerate(dom_spec.get('nics', [])):
                if 'ip' in nic:
                    continue

                net = conf['nets'][nic['net']]
                if net['type'] != 'nat':
                    continue

                allocated = net['mapping'].values()
                vacant = _create_ip(
                    net['gw'],
                    set(range(2, 255)).difference(
                        set(
                            [
                                int(ip.split('.')[-1]) for ip in allocated
                            ]
                        )
                    ).pop()
                )
                nic['ip'] = vacant
                self._add_nic_to_mapping(net, dom_spec, nic)

    def _config_net_topology(self, conf):
        self._init_net_specs(conf)
        self._check_predefined_subnets(conf)
        allocated_subnets = self._allocate_subnets(conf)
        try:
            self._register_preallocated_ips(conf)
            self._allocate_ips_to_nics(conf)
        except:
            for subnet in allocated_subnets:
                subnet_lease.release(subnet)
            raise

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

    def _use_prototype(
        self,
        spec,
        conf
    ):
        prototype = conf['prototypes'][spec['based-on']]
        del spec['based-on']
        for attr in prototype:
            if attr not in spec:
                spec[attr] = copy.deepcopy(prototype[attr])
        return spec

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

            for name, spec in conf['domains'].items():
                if 'based-on' in spec:
                    spec = self._use_prototype(spec, conf)
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

            self._config_net_topology(conf)

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
