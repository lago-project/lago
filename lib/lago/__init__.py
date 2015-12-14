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
import functools
import json
import logging
import os
import shutil
import uuid

import paths
import subnet_lease
import utils
import virt
import log_utils


LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)
log_task = functools.partial(log_utils.log_task, logger=LOGGER)


def _create_ip(subnet, index):
    """
    Given a subnet or an ip and an index returns the ip with that lower index
    from the subnet (255.255.255.0 mask only subnets)

    Args:
        subnet (str): Strign containing the three first elements of the decimal
            representation of a subnet (X.Y.Z) or a full ip (X.Y.Z.A)
        index (int or str): Last element of a decimal ip representation, for
            example, 123 for the ip 1.2.3.123

    Returns:
        str: The dotted decimal representation of the ip
    """
    return '.'.join(subnet.split('.')[:3] + [str(index)])


def _ip_in_subnet(subnet, ip):
    """
    Checks if an ip is included in a subnet.

    Note:
        only 255.255.255.0 masks allowed

    Args:
        subnet (str): Strign containing the three first elements of the decimal
            representation of a subnet (X.Y.Z) or a full ip (X.Y.Z.A)
        ip (str or int): Decimal ip representation

    Returns:
        bool: ``True`` if ip is in subnet, ``False`` otherwise
    """
    return (
        _create_ip(subnet, 1) == _create_ip(ip, 1)
        or
        '0.0.0.1' == _create_ip(ip, 1)
    )


class Prefix(object):
    """
    A prefix is a directory that will contain all the data needed to setup the
    environment.

    Attributes:
        _prefix (str): Path to the directory of this prefix
        _paths (lago.path.Paths): Path handler class
        _virt_env (lago.virt.VirtEnv): Lazily loaded virtual env handler
        _metadata (dict): Lazily loaded metadata
    """
    def __init__(self, prefix):
        """
        Args:
            prefix (str): Path of the prefix
        """
        self._prefix = prefix
        self._paths = self._create_paths()
        self._virt_env = None
        self._metadata = None

    def _create_paths(self):
        """
        Get the path handler for this instance

        Returns:
            lago.paths.Paths: Path handler
        """
        return paths.Paths(self._prefix)

    def _get_metadata(self):
        """
        Retrieve the metadata info for this prefix

        Returns:
            dict: metadata info
        """
        if self._metadata is None:
            try:
                with open(self.paths.metadata()) as f:
                    self._metadata = json.load(f)
            except IOError:
                self._metadata = {}
        return self._metadata

    def _save_metadata(self):
        """
        Write this prefix metadata to disk

        Returns:
            None
        """
        with open(self.paths.metadata(), 'w') as f:
            utils.json_dump(self._get_metadata(), f)

    def save(self):
        """
        Save this prefix to persistent storage

        Returns:
            None
        """
        self._save_metadata()
        self.virt_env.save()

    @property
    def paths(self):
        """
        Access the path handler for this prefix

        Returns:
            lago.paths.Paths: Path handler
        """
        return self._paths

    def _create_ssh_keys(self):
        """
        Generate a pair of ssh keys for this prefix

        Returns:
            None

        Raises:
            RuntimeError: if it fails to create the keys
        """
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

    @log_task('Initialize prefix')
    def initialize(self):
        """
        Initialize this prefix, this includes creating the destination path,
        and creating the uuid for the prefix, for any other actions see
        :func:`Prefix.virt_conf`

        Will safely roll back if any of those steps fail

        Returns:
            None

        Raises:
            RuntimeError: If it fails to create the prefix dir
        """
        prefix = self.paths.prefix()
        with utils.RollbackContext() as rollback:
            with LogTask('Create prefix dirs'):
                try:
                    os.mkdir(prefix)
                except OSError:
                    raise RuntimeError(
                        'Could not create prefix at %s' % prefix
                    )
            rollback.prependDefer(shutil.rmtree, prefix)

            with open(self.paths.uuid(), 'w') as f, \
                    LogTask('Generate prefix uuid'):
                f.write(uuid.uuid1().hex)

            with LogTask('Create ssh keys'):
                self._create_ssh_keys()

            with LogTask('Tag prefix as initialized'):
                with open(self.paths.prefix_lagofile(), 'w') as fd:
                    fd.write('')

            rollback.clear()

    @log_task('Cleanup prefix')
    def cleanup(self):
        """
        Stops any running entities in the prefix and uninitializes it, usually
        you want to do this if you are going to remove the prefix afterwards

        Returns:
            None
        """
        with LogTask('Stop prefix'):
            self.stop()
        with LogTask("Tag prefix as uninitialized"):
            os.unlink(self.paths.prefix_lagofile())

    def _init_net_specs(self, conf):
        """
        Given a configuration specification, initializes all the net
        definitions in it so they can be used comfortably

        Args:
            conf (dict): Configuration specification

        Returns:
            None
        """
        for net_name, net_spec in conf.get('nets', {}).items():
            net_spec['name'] = net_name
            net_spec['mapping'] = {}
            net_spec.setdefault('type', 'nat')

    def _check_predefined_subnets(self, conf):
        """
        Checks if all of the nets defined in the config are inside the allowed
        range, throws exception if not

        Args:
            conf (dict): Configuration spec where to get the nets definitions
                from

        Returns:
            None

        Raises:
            RuntimeError: If there are any subnets out of the allowed range
        """
        for net_name, net_spec in conf.get('nets', {}).items():
            subnet = net_spec.get('gw')
            if subnet is None:
                continue

            if subnet_lease.is_leasable_subnet(subnet):
                raise RuntimeError(
                    '%s subnet can only be dynamically allocated' % (subnet)
                )

    def _allocate_subnets(self, conf):
        """
        Allocate all the subnets needed by the given configuration spec

        Args:
            conf (dict): Configuration spec where to get the nets definitions
                from

        Returns:
            list: allocated subnets
        """
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
        """
        Populates the given net spec mapping entry with the nicks of the given
        domain

        Args:
            net (dict): Network spec to populate
            dom (dict): libvirt domain specification
            nic (str): Name of the interface to add to the net mapping from the
                domain

        Returns:
            None
        """
        dom_name = dom['name']
        idx = dom['nics'].index(nic)
        name = idx == 0 and dom_name or '%s-eth%d' % (dom_name, idx)
        net['mapping'][name] = nic['ip']

    def _register_preallocated_ips(self, conf):
        """
        Parse all the domains in the given conf and preallocate all their ips
        into the networks mappings, raising exception on duplicated ips or ips
        out of the allowed ranges

        See Also:
            :mod:`lago.subnet_lease`

        Args:
            conf (dict): Configuration spec to parse

        Returns:
            None

        Raises:
            RuntimeError: if there are any duplicated ips or any ip out of the
                allowed range
        """
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
                        "%s:nic%d's IP [%s] is outside the subnet [%s]"
                        % (
                            dom_name,
                            dom_spec['nics'].index(nic),
                            nic['ip'],
                            net['gw'],
                        ),
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
                        )
                    )

                self._add_nic_to_mapping(net, dom_spec, nic)

    def _allocate_ips_to_nics(self, conf):
        """
        For all the nics of all the domains in the conf that have dynamic ip,
        allocate one and addit to the network mapping

        Args:
            conf (dict): Configuration spec to extract the domains from

        Returns:
            None
        """
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
        """
        Initialize and populate all the network related elements, like
        reserving ips and populating network specs of the given confiiguration
        spec

        Args:
            conf (dict): Configuration spec to initalize

        Returns:
            None
        """
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
        """
        Creates a disc with the given name from the given repo or store.

        Args:
            name (str): Name of the domain to create the disk for
            spec (dict): Specification of the disk to create
            template_repo (TemplateRepository or None): template repo instance
                to use
            template_store (TemplateStore or None): template store instance to
                use

        Returns:
            Tuple(str, dict): Path with the disk and metadata

        Raises:
            RuntimeError: If the type of the disk is not supported or failed to
                create the disk
        """
        with LogTask("Create disk %s" % spec['name']):
            LOGGER.debug("Spec: %s" % spec)
            disk_metadata = {}

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
                    LOGGER.info(
                        log_utils.log_always(
                            "Template %s not in cache, downloading"
                        ) % template_version.name,
                    )
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

                task_message = 'Create disk %s(%s)' % (name, spec['name'])
            elif spec['type'] == 'empty':
                qemu_img_cmd = ['qemu-img', 'create', '-f', spec['format'],
                                disk_path, spec['size']]
                task_message = 'Create empty disk image'
            elif spec['type'] == 'file':
                # If we're using raw file, just return it's path
                return spec['path'], disk_metadata
            else:
                raise RuntimeError('Unknown drive spec %s' % str(spec))

            if os.path.exists(disk_path):
                os.unlink(disk_path)

            with LogTask(task_message):
                ret, _, _ = utils.run_command(qemu_img_cmd)
                if ret != 0:
                    raise RuntimeError(
                        'Failed to create image, qemu-img returned %d' % ret,
                    )
                # To avoid losing access to the file
                os.chmod(disk_path, 0666)

            return disk_path, disk_metadata

    def _use_prototype(
        self,
        spec,
        conf
    ):
        """
        Populates the given spec with the values of it's declared prototype

        Args:
            spec (dict): spec to update
            conf (dict): Configuration spec containing the prototypes

        Returns:
            dict: updated spec
        """
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
        """
        Initializes all the virt infrastructure of the prefix, creating the
        domains disks, doing any network leases and creating all the virt
        related files and dirs inside this prefix.

        Args:
            conf (dict): Configuration spec
            template_repo (TemplateRepository): template repository intance
            template_store (TemplateStore): template store instance

        Returns:
            None
        """
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
                with LogTask('Create disks for VM %s' % name):
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
        """
        Start this prefix

        Returns:
            None
        """
        self.virt_env.start()

    def stop(self):
        """
        Stop this prefix

        Returns:
            None
        """
        self.virt_env.stop()

    def create_snapshots(self, name):
        """
        Creates one snapshot on all the domains with the given name

        Args:
            name (str): Name of the snapshots to create

        Returns:
            None
        """
        self.virt_env.create_snapshots(name)

    def revert_snapshots(self, name):
        """
        Revert all the snapshots with the given name from all the domains

        Args:
            name (str): Name of the snapshots to revert

        Returns:
            None
        """
        self.virt_env.revert_snapshots(name)

    def _create_virt_env(self):
        """
        Create a new virt env from this prefix

        Returns:
            lago.virt.VirtEnv: virt env created from this prefix
        """
        return virt.VirtEnv.from_prefix(self)

    @property
    def virt_env(self):
        """
        Getter for this instance's virt env, creates it if needed

        Returns:
            lago.virt.VirtEnv: virt env instance used by this prefix
        """
        if self._virt_env is None:
            self._virt_env = self._create_virt_env()
        return self._virt_env
