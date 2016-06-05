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
import glob
import json
import logging
import os
import shutil
import subprocess
import urlparse
import urllib
import uuid
import warnings
from os.path import join

import xmltodict

import paths
import subnet_lease
import utils
import virt
import log_utils

from .plugins import prefix

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
        or '0.0.0.1' == _create_ip(ip, 1)
    )


class DefaultPrefix(prefix.PrefixPlugin):
    """
    A prefix is a directory that will contain all the data needed to setup the
    environment.

    Attributes:
        _prefix (str): Path to the directory of this prefix
        _paths (lago.path.Paths): Path handler class
        _virt_env (lago.virt.VirtEnv): Lazily loaded virtual env handler
        _metadata (dict): Lazily loaded metadata
    """
    VIRT_ENV_CLASS = virt.VirtEnv

    def __init__(self, prefix):
        """
        Args:
            prefix (str): Path of the prefix
        """
        self._prefix = prefix
        self.paths = paths.Paths(self._prefix)
        self._virt_env = None
        self._metadata = None

    def _get_metadata(self):
        """
        Retrieve the metadata info for this prefix

        Returns:
            dict: metadata info
        """
        if self._metadata is None:
            try:
                with open(self.paths.metadata()) as metadata_fd:
                    json_data = metadata_fd.read()
                    if json_data:
                        self._metadata = json.load(json_data)
                    else:
                        raise IOError()
            except IOError:
                self._metadata = {}
        return self._metadata

    def _save_metadata(self):
        """
        Write this prefix metadata to disk

        Returns:
            None
        """
        with open(self.paths.metadata(), 'w') as metadata_fd:
            utils.json_dump(self._get_metadata(), metadata_fd)

    def save(self):
        """
        Save this prefix to persistent storage

        Returns:
            None
        """
        if not os.path.exists(self.paths.virt()):
            os.makedirs(self.paths.virt())

        self._save_metadata()
        self.virt_env.save()

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
                '-t',
                'rsa',
                '-N',
                '',
                '-f',
                self.paths.ssh_id_rsa(),
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
        prefix = self.paths.prefix
        os.environ['LAGO_PREFIX_PATH'] = prefix
        os.environ['LAGO_WORKDIR_PATH'] = os.path.dirname(prefix)

        with utils.RollbackContext() as rollback:
            with LogTask('Create prefix dirs'):
                try:
                    os.mkdir(prefix)
                except OSError as error:
                    raise RuntimeError(
                        'Could not create prefix at %s:\n%s' % (prefix, error)
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

    @staticmethod
    def _init_net_specs(conf):
        """
        Given a configuration specification, initializes all the net
        definitions in it so they can be used comfortably

        Args:
            conf (dict): Configuration specification

        Returns:
            dict: the adapted new conf
        """
        for net_name, net_spec in conf.get('nets', {}).items():
            net_spec['name'] = net_name
            net_spec['mapping'] = {}
            net_spec.setdefault('type', 'nat')

        return conf

    @staticmethod
    def _check_predefined_subnets(conf):
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
        for net_spec in conf.get('nets', {}).itervalues():
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
            tuple(list, dict): allocated subnets and modified conf
        """
        allocated_subnets = []
        try:
            for net_spec in conf.get('nets', {}).itervalues():
                if 'gw' in net_spec or net_spec['type'] != 'nat':
                    continue
                net_spec['gw'] = subnet_lease.acquire(self.paths.uuid())
                allocated_subnets.append(net_spec['gw'])
        except:
            for subnet in allocated_subnets:
                subnet_lease.release(subnet)

        return allocated_subnets, conf

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
                        net['gw'], int(nic['ip'].split('.')[-1])
                    )

                dom_name = dom_spec['name']
                if not _ip_in_subnet(net['gw'], nic['ip']):
                    raise RuntimeError(
                        "%s:nic%d's IP [%s] is outside the subnet [%s]" % (
                            dom_name,
                            dom_spec['nics'].index(nic),
                            nic['ip'],
                            net['gw'],
                        ),
                    )

                if nic['ip'] in net['mapping'].values():
                    conflict_list = [
                        name
                        for name, ip in net['mapping'].items()
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
                    net['gw'], set(range(2, 255)).difference(
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
        conf = self._init_net_specs(conf)
        self._check_predefined_subnets(conf)
        allocated_subnets, conf = self._allocate_subnets(conf)
        try:
            self._register_preallocated_ips(conf)
            self._allocate_ips_to_nics(conf)
        except:
            for subnet in allocated_subnets:
                subnet_lease.release(subnet)
            raise

        return conf

    def _create_disk(
        self,
        name,
        spec,
        template_repo=None,
        template_store=None,
    ):
        """
        Creates a disc with the given name from the given repo or store

        Args:
            name (str): Name of the domain to create the disk for
            spec (dict): Specification of the disk to create
            template_repo (TemplateRepository or None): template repo instance
                to use
            template_store (TemplateStore or None): template store instance to
                use

        Returns:
            Tuple(str, dict): Path to the disk and disk metadata

        Raises:
            RuntimeError: If the type of the disk is not supported or failed to
                create the disk
        """
        LOGGER.debug("Spec: %s" % spec)
        with LogTask("Create disk %s" % spec['name']):
            disk_metadata = {}

            if spec['type'] == 'template':
                disk_path, disk_metadata = self._handle_template(
                    host_name=name,
                    template_spec=spec,
                    template_repo=template_repo,
                    template_store=template_store,
                )
            elif spec['type'] == 'empty':
                disk_path, disk_metadata = self._handle_empty_disk(
                    host_name=name,
                    disk_spec=spec,
                )
            elif spec['type'] == 'file':
                disk_path, disk_metadata = self._handle_file_disk(
                    disk_spec=spec,
                )
            else:
                raise RuntimeError('Unknown drive spec %s' % str(spec))

            return disk_path, disk_metadata

    def _handle_file_disk(self, disk_spec):
        url = os.path.expandvars(disk_spec.get('url', ''))
        disk_path = os.path.expandvars(disk_spec.get('path', ''))
        disk_metadata = disk_spec.get('metadata', {})
        if not url and not disk_path:
            raise RuntimeError(
                'Partial drive spec, no url nor path provided for disk of '
                'type file:\n%s' % str(disk_spec)
            )

        if url:
            disk_spec['path'] = self._retrieve_disk_url(url, disk_path)
        else:
            disk_spec['path'] = disk_path

        # If we're using raw file, return its path
        disk_path = disk_spec['path']
        return disk_path, disk_metadata

    def _retrieve_disk_url(self, disk_url, disk_dst_path=None):
        disk_in_prefix = self.fetch_url(disk_url)
        if disk_dst_path is None:
            return disk_in_prefix
        else:
            shutil.move(disk_in_prefix, disk_dst_path)
            return disk_dst_path

    @staticmethod
    def _generate_disk_name(host_name, disk_name, disk_format):
        return '%s_%s.%s' % (host_name, disk_name, disk_format, )

    def _generate_disk_path(self, disk_name):
        return os.path.expandvars(self.paths.images(disk_name))

    def _handle_empty_disk(self, host_name, disk_spec):
        disk_metadata = disk_spec.get('metadata', {})
        disk_filename = self._generate_disk_name(
            host_name=host_name,
            disk_name=disk_spec['name'],
            disk_format=disk_spec['format'],
        )
        disk_path = self._generate_disk_path(disk_name=disk_filename)

        qemu_cmd = ['qemu-img', 'create']
        if disk_spec['format'] == 'qcow2':
            qemu_cmd += [
                '-f', disk_spec['format'], '-o', 'preallocation=metadata'
            ]
        else:
            qemu_cmd += ['-f', disk_spec['format']]

        qemu_cmd += [disk_path, disk_spec['size']]

        if os.path.exists(disk_path):
            os.unlink(disk_path)

        with LogTask(
            'Create empty disk %s(%s)' % (host_name, disk_spec['name'])
        ):
            self._run_qemu(qemu_cmd, disk_path)

        disk_rel_path = os.path.join(
            '$LAGO_PREFIX_PATH',
            os.path.basename(self.paths.images()),
            os.path.basename(disk_path),
        )
        return disk_rel_path, disk_metadata

    @staticmethod
    def _run_qemu(qemu_cmd, disk_path):
        ret = utils.run_command(qemu_cmd)
        if ret.code != 0:
            raise RuntimeError(
                'Failed to create image, qemu-img returned %d:\n'
                'out:%s\nerr:%s' % ret,
            )
        # To avoid losing access to the file
        os.chmod(disk_path, 0666)
        return ret

    def _handle_template(
        self,
        host_name,
        template_spec,
        template_store=None,
        template_repo=None
    ):
        template_type = template_spec.get('template_type', 'lago')
        disk_filename = self._generate_disk_name(
            host_name=host_name,
            disk_name=template_spec['name'],
            disk_format=template_spec['format'],
        )
        disk_path = self._generate_disk_path(disk_name=disk_filename)
        if template_type == 'lago':
            qemu_cmd, disk_metadata = self._handle_lago_template(
                disk_path=disk_path,
                template_spec=template_spec,
                template_store=template_store,
                template_repo=template_repo,
            )
        elif template_type == 'qcow2':
            qemu_cmd, disk_metadata = self._handle_qcow_template(
                disk_path=disk_path,
                template_spec=template_spec,
            )
        else:
            raise RuntimeError(
                'Unsupporte template spec %s' % str(template_spec)
            )

        if os.path.exists(disk_path):
            os.unlink(disk_path)

        with LogTask(
            'Create disk %s(%s)' % (host_name, template_spec['name'])
        ):
            self._run_qemu(qemu_cmd, disk_path)

        # Update the path as relative so it can be relocated
        disk_rel_path = os.path.join(
            '$LAGO_PREFIX_PATH',
            os.path.basename(self.paths.images()),
            os.path.basename(disk_path),
        )
        return disk_rel_path, disk_metadata

    def _handle_qcow_template(self, disk_path, template_spec):
        base_path = template_spec.get('path', '')
        if not base_path:
            raise RuntimeError('Partial drive spec %s' % str(template_spec))

        qemu_cmd = [
            'qemu-img', 'create', '-f', 'qcow2', '-b', base_path, disk_path
        ]
        disk_metadata = template_spec.get('metadata', {})
        return qemu_cmd, disk_metadata

    def _handle_lago_template(
        self, disk_path, template_spec, template_store, template_repo
    ):
        disk_metadata = template_spec.get('metadata', {})
        if template_store is None or template_repo is None:
            raise RuntimeError('No templates directory provided')

        template = template_repo.get_by_name(template_spec['template_name'])
        template_version = template.get_version(
            template_spec.get('template_version', None)
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
        qemu_cmd = ['qemu-img', 'create', '-f', 'qcow2', '-b', base, disk_path]
        return qemu_cmd, disk_metadata

    def _ova_to_spec(self, filename):
        """
        Retrieve the given ova and makes a template of it.
        Creates a disk from network provided ova.
        Calculates the needed memory from the ovf.
        The disk will be cached in the template repo

        Args:
            filename(str): the url to retrive the data from

        TODO:
            * Add hash checking against the server
              for faster download and latest version
            * Add config script running on host - other place
            * Add cloud init support - by using cdroms in other place
            * Handle cpu in some way - some other place need to pick it up
            * Handle the memory units properly - we just assume MegaBytes

        Returns:
            list of dict: list with the disk specification
            int: VM memory, None if none defined
            int: Number of virtual cpus, None if none defined

        Raises:
            RuntimeError: If the ova format is not supported
            TypeError: If the memory units in the ova are noot supported
                (currently only 'MegaBytes')
        """
        # extract if needed
        ova_extracted_dir = os.path.splitext(filename)[0]

        if not os.path.exists(ova_extracted_dir):
            os.makedirs(ova_extracted_dir)
            subprocess.check_output(
                [
                    "tar", "-xvf", filename, "-C", ova_extracted_dir
                ],
                stderr=subprocess.STDOUT
            )

        # lets find the ovf file
        # we expect only one to be
        ovf = glob.glob(ova_extracted_dir + "/master/vms/*/*.ovf")
        if len(ovf) != 1:
            raise RuntimeError("We support only one vm in ova")

        image_file = None
        memory = None
        vcpus = None
        # we found our ovf
        # lets extract the resources
        with open(ovf[0]) as fd:
            # lets extract the items
            obj = xmltodict.parse(fd.read())
            hardware_items = [
                section
                for section in obj["ovf:Envelope"]["Content"]["Section"]
                if section["@xsi:type"] == "ovf:VirtualHardwareSection_Type"
            ]

            if len(hardware_items) != 1:
                raise RuntimeError("We support only one machine desc in ova")
            hardware_items = hardware_items[0]

            for item in hardware_items["Item"]:
                # lets test resource types
                CPU_RESOURCE = 3
                MEMORY_RESOURCE = 4
                DISK_RESOURCE = 17

                resource_type = int(item["rasd:ResourceType"])
                if resource_type == CPU_RESOURCE:
                    vcpus = int(item["rasd:cpu_per_socket"]) * \
                        int(item["rasd:num_of_sockets"])

                elif resource_type == MEMORY_RESOURCE:
                    memory = int(item["rasd:VirtualQuantity"])
                    if item["rasd:AllocationUnits"] != "MegaBytes":
                        raise TypeError(
                            "Fix me : we need to suport other units too"
                        )

                elif resource_type == DISK_RESOURCE:
                    image_file = item["rasd:HostResource"]

        if image_file is not None:
            disk_meta = {"root-partition": "/dev/sda1"}
            disk_spec = [{"type": "template",
                          "template_type": "qcow2",
                          "format": "qcow2",
                          "dev": "vda",
                          "name": "root",
                          "name": os.path.basename(image_file),
                          "path": ova_extracted_dir +
                                 "/images/" + image_file,
                          "metadata": disk_meta}]

        return disk_spec, memory, vcpus

    def _use_prototype(self, spec, prototypes):
        """
        Populates the given spec with the values of it's declared prototype

        Args:
            spec (dict): spec to update
            prototypes (dict): Configuration spec containing the prototypes

        Returns:
            dict: updated spec
        """
        prototype = spec['based-on']
        del spec['based-on']
        for attr in prototype:
            if attr not in spec:
                spec[attr] = copy.deepcopy(prototype[attr])

        return spec

    def fetch_url(self, url):
        """
        Retrieves the given url to the prefix

        Args:
            url(str): Url to retrieve

        Returns:
            str: path to the downloaded file
        """
        url_path = urlparse.urlsplit(url).path
        dst_path = os.path.basename(url_path)
        dst_path = self.paths.prefixed(dst_path)
        with LogTask('Downloading %s' % url):
            urllib.urlretrieve(url=os.path.expandvars(url), filename=dst_path)

        return dst_path

    def virt_conf_from_stream(
        self,
        conf_fd,
        template_repo=None,
        template_store=None,
        do_bootstrap=True,
    ):
        """
        Initializes all the virt infrastructure of the prefix, creating the
        domains disks, doing any network leases and creating all the virt
        related files and dirs inside this prefix.

        Args:
            conf_fd (File): File like object to read the config from
            template_repo (TemplateRepository): template repository intance
            template_store (TemplateStore): template store instance

        Returns:
            None
        """
        virt_conf = utils.load_virt_stream(conf_fd)
        LOGGER.debug('Loaded virt config:\n%s', virt_conf)
        return self.virt_conf(
            conf=virt_conf,
            template_repo=template_repo,
            template_store=template_store,
            do_bootstrap=do_bootstrap,
        )

    def _prepare_domains_images(self, conf, template_repo, template_store):
        if not os.path.exists(self.paths.images()):
            os.makedirs(self.paths.images())

        for name, domain_spec in conf['domains'].items():
            if not name:
                raise RuntimeError(
                    'An invalid (empty) domain name was found in the '
                    'configuration file. Cannot continue. A name must be '
                    'specified for the domain'
                )

            domain_spec['name'] = name
            conf['domains'][name] = self._prepare_domain_image(
                domain_spec=domain_spec,
                prototypes=conf.get('prototypes', {}),
                template_repo=template_repo,
                template_store=template_store,
            )

        return conf

    def _prepare_domain_image(
        self, domain_spec, prototypes, template_repo, template_store
    ):
        if 'based-on' in domain_spec:
            domain_spec = self._use_prototype(
                spec=domain_spec,
                prototypes=prototypes,
            )

        if domain_spec.get('type', '') == 'ova':
            domain_spec = self._handle_ova_image(domain_spec=domain_spec)

        with LogTask('Create disks for VM %s' % domain_spec['name']):
            domain_spec['disks'] = self._create_disks(
                domain_name=domain_spec['name'],
                disks_specs=domain_spec.get('disks', []),
                template_repo=template_repo,
                template_store=template_store,
            )

        return domain_spec

    def _handle_ova_image(self, domain_spec):
        # we import the ova to template
        domain_spec['type'] = 'template'
        ova_file = self.fetch_url(domain_spec['url'])
        ova_disk, domain_spec["memory"], domain_spec[
            "vcpu"
        ] = self._ova_to_spec(ova_file)
        if "disks" not in domain_spec.keys():
            domain_spec["disks"] = ova_disk
        else:
            domain_spec["disks"] = ova_disk + domain_spec["disks"]

        return domain_spec

    def _create_disks(
        self, domain_name, disks_specs, template_repo, template_store
    ):
        new_disks = []
        for disk in disks_specs:
            path, metadata = self._create_disk(
                name=domain_name,
                spec=disk,
                template_repo=template_repo,
                template_store=template_store,
            )
            new_disks.append(
                {
                    'path': path,
                    'dev': disk['dev'],
                    'format': disk['format'],
                    'metadata': metadata,
                    'type': disk['type']
                },
            )

        return new_disks

    def virt_conf(
        self,
        conf,
        template_repo=None,
        template_store=None,
        do_bootstrap=True
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
        os.environ['LAGO_PREFIX_PATH'] = self.paths.prefix
        with utils.RollbackContext() as rollback:
            rollback.prependDefer(
                shutil.rmtree,
                self.paths.prefix,
                ignore_errors=True
            )
            conf = self._prepare_domains_images(
                conf=conf,
                template_repo=template_repo,
                template_store=template_store,
            )
            conf = self._config_net_topology(conf)

            conf['domains'] = self._copy_deploy_scripts_for_hosts(
                domains=conf['domains']
            )
            self._virt_env = self.VIRT_ENV_CLASS(
                prefix=self,
                vm_specs=conf['domains'],
                net_specs=conf['nets'],
            )
            if do_bootstrap:
                self.virt_env.bootstrap()

            self.save()
            rollback.clear()

    def start(self, vm_names=None):
        """
        Start this prefix

        Args:
            vm_names(list of str): List of the vms to start

        Returns:
            None
        """
        self.virt_env.start(vm_names=vm_names)

    def stop(self, vm_names=None):
        """
        Stop this prefix

        Args:
            vm_names(list of str): List of the vms to stop

        Returns:
            None
        """
        self.virt_env.stop(vm_names=vm_names)

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

    def get_snapshots(self):
        """
        Retrieve info on all the snapshots from all the domains

        Returns:
            dict of str: list(str): dictionary with vm_name -> snapshot list
        """
        return self.virt_env.get_snapshots()

    def _create_virt_env(self):
        """
        Create a new virt env from this prefix

        Returns:
            lago.virt.VirtEnv: virt env created from this prefix
        """
        return self.VIRT_ENV_CLASS.from_prefix(self)

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

    def destroy(self):
        """
        Destroy this prefix, running any cleanups and removing any files
        inside it.
        """
        self.cleanup()
        shutil.rmtree(self._prefix)

    def get_vms(self):
        """
        Retrieve info on all the vms

        Returns:
            dict of str->list(str): dictionary with vm_name -> vm list
        """
        return self.virt_env.get_vms()

    def get_nets(self):
        """
        Retrieve info on all the nets from all the domains

        Returns:
            dict of str->list(str): dictionary with net_name -> net list
        """
        return self.virt_env.get_nets()

    @classmethod
    def resolve_prefix_path(cls, start_path=None):
        """
        Look for an existing prefix in the given path, in a path/.lago dir, or
        in a .lago dir under any of it's parent directories

        Args:
            start_path (str): path to start the search from, if None passed, it
                will use the current dir

        Returns:
            str: path to the found prefix

        Raises:
            RuntimeError: if no prefix was found
        """
        if not start_path or start_path == 'auto':
            start_path = os.path.curdir

        cur_path = start_path
        LOGGER.debug('Checking if %s is a prefix', os.path.abspath(cur_path))
        if cls.is_prefix(cur_path):
            return os.path.abspath(cur_path)

        # now search for a .lago directory that's a prefix on any parent dir
        cur_path = join(start_path, '.lago')
        while not cls.is_prefix(cur_path):
            LOGGER.debug('%s  is not a prefix', cur_path)
            cur_path = os.path.normpath(
                os.path.join(cur_path, '..', '..', '.lago')
            )
            LOGGER.debug('Checking %s for a prefix', cur_path)
            if os.path.realpath(join(cur_path, '..')) == '/':
                raise RuntimeError(
                    'Unable to find prefix for %s' %
                    os.path.abspath(start_path)
                )

        return os.path.abspath(cur_path)

    @classmethod
    def is_prefix(cls, path):
        """
        Check if a path is a valid prefix

        Args:
            path(str): path to be checked

        Returns:
            bool: True if the given path is a prefix
        """
        lagofile = paths.Paths(path).prefix_lagofile()
        return os.path.isfile(lagofile)

    @log_task('Collect artifacts')
    def collect_artifacts(self, output_dir):
        if os.path.exists(output_dir):
            utils.rotate_dir(output_dir)

        os.makedirs(output_dir)

        def _collect_artifacts(vm):
            with LogTask('%s' % vm.name()):
                path = os.path.join(output_dir, vm.name())
                os.makedirs(path)
                vm.collect_artifacts(path)

        utils.invoke_in_parallel(
            _collect_artifacts,
            self.virt_env.get_vms().values(),
        )

    def _get_scripts(self, host_metadata):
        """
        Temporary method to retrieve the host scripts

        TODO:
            remove once the "ovirt-scripts" option gets deprecated

        Args:
            host_metadata(dict): host metadata to retrieve the scripts for

        Returns:
            list: deploy scripts for the host, empty if none found
        """
        deploy_scripts = host_metadata.get('deploy-scripts', [])
        if deploy_scripts:
            return deploy_scripts

        ovirt_scripts = host_metadata.get('ovirt-scripts', [])
        if ovirt_scripts:
            warnings.warn(
                'Deprecated entry "ovirt-scripts" will not be supported in '
                'the future, replace with "deploy-scripts"'
            )

        return ovirt_scripts

    def _set_scripts(self, host_metadata, scripts):
        """
        Temporary method to set the host scripts

        TODO:
            remove once the "ovirt-scripts" option gets deprecated

        Args:
            host_metadata(dict): host metadata to set scripts in

        Returns:
            dict: the updated metadata
        """
        scripts_key = 'deploy-scripts'
        if 'ovirt-scritps' in host_metadata:
            scripts_key = 'ovirt-scripts'

        host_metadata[scripts_key] = scripts
        return host_metadata

    def _copy_deploy_scripts_for_hosts(self, domains):
        """
        Copy the deploy scripts for all the domains into the prefix scripts dir

        Args:
            domains(dict): spec with the domains info as when loaded from the
                initfile

        Returns:
            None
        """
        with LogTask('Copying any deploy scripts'):
            for host_name, host_spec in domains.iteritems():
                host_metadata = host_spec.get('metadata', {})
                deploy_scripts = self._get_scripts(host_metadata)
                new_scripts = self._copy_delpoy_scripts(deploy_scripts)
                self._set_scripts(
                    host_metadata=host_metadata,
                    scripts=new_scripts,
                )

        return domains

    def _copy_delpoy_scripts(self, scripts):
        """
        Copy the given deploy scripts to the scripts dir in the prefix

        Args:
            scripts(list of str): list of paths of the scripts to copy to the
                prefix

        Returns:
            list of str: list with the paths to the copied scripts, with a
                prefixed with $LAGO_PREFIX_PATH so the full path is not
                hardcoded
        """
        if not os.path.exists(self.paths.scripts()):
            os.makedirs(self.paths.scripts())

        new_scripts = []
        for script in scripts:
            script = os.path.expandvars(script)
            if not os.path.exists(script):
                raise RuntimeError('Script %s does not exist' % script)

            sanitized_name = script.replace('/', '_')
            new_script_cur_path = os.path.expandvars(
                self.paths.scripts(sanitized_name)
            )
            shutil.copy(script, new_script_cur_path)

            new_script_init_path = os.path.join(
                '$LAGO_PREFIX_PATH',
                os.path.basename(self.paths.scripts()),
                sanitized_name,
            )
            new_scripts.append(new_script_init_path)

        return new_scripts

    def _deploy_host(self, host):
        with LogTask('Deploy VM %s' % host.name()):
            deploy_scripts = self._get_scripts(host.metadata)
            if not deploy_scripts:
                return

            with LogTask('Wait for ssh connectivity'):
                host.wait_for_ssh()

            for script in deploy_scripts:
                script = os.path.expanduser(os.path.expandvars(script))
                with LogTask('Run script %s' % os.path.basename(script)):
                    ret, out, err = host.ssh_script(script, show_output=False)

                if ret != 0:
                    LOGGER.debug('STDOUT:\n%s' % out)
                    LOGGER.error('STDERR\n%s' % err)
                    raise RuntimeError(
                        '%s failed with status %d on %s' % (
                            script,
                            ret,
                            host.name(),
                        ),
                    )

    @log_task('Deploy environment')
    def deploy(self):
        utils.invoke_in_parallel(
            self._deploy_host, self.virt_env.get_vms().values()
        )
