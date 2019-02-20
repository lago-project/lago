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
"""
VM Plugins
============
There are two VM-related plugin extension points, there's the
VM Type Plugin, that allows you to modify at a higher level the inner
workings of the VM class (domain concept in the initfile).
The other plugin extension point, the [VM Provider Plugin], that allows you to
create an alternative implementation of the provisioning details for the VM,
for example, using a remote libvirt instance or similar.
"""
from copy import deepcopy
import contextlib
import errno
import functools
from future.builtins import super
import logging
import os
import shutil
import tempfile
import warnings
from abc import (ABCMeta, abstractmethod)
from scp import SCPClient, SCPException

from .. import (
    utils,
    log_utils,
    plugins,
    ssh,
)
from lago.config import config

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)


class VMError(utils.LagoException):
    pass


class ExtractPathError(VMError):
    pass


class ExtractPathNoPathError(VMError):
    def __init__(self, err):
        super().__init__('Failed to extract files: {}'.format(err))


class LagoVMNotRunningError(utils.LagoUserException):
    def __init__(self, vm_name):
        super().__init__('VM {} is not running'.format(vm_name))


class LagoCopyFilesToVMError(utils.LagoUserException):
    def __init__(self, local_files, err):
        super().__init__(
            'Failed to copy files/directory {}\n{}'.format(local_files, err)
        )


class LagoCopyFilesFromVMError(utils.LagoUserException):
    def __init__(self, remote_files, local_files, err=''):
        super().__init__(
            'Failed to copy files/directory from {} to {}\n{}'.format(
                remote_files, local_files, err
            )
        )


class LagoVMDoesNotExistError(utils.LagoException):
    pass


class LagoFailedToGetVMStateError(utils.LagoException):
    pass


def check_running(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.running():
            raise LagoVMNotRunningError(self.name())
        return func(self, *args, **kwargs)

    return wrapper


class VMProviderPlugin(plugins.Plugin):
    """
    If you want to use a custom provider for you VMs (say, ovirt for example),
    you have to inherit from this class, and then define the
    'default_vm_provider' in your config to be your plugin, or explicitly
    specify it on each domain definition in the initfile with 'vm-provider' key
    You will have to override at least all the abstractmethods in order to
    write a provider plugin, even if they are just runnig `pass`.
    """

    def __init__(self, vm):
        self.vm = vm

    @abstractmethod
    def start(self, *args, **kwargs):
        """
        Start a domain
        Returns:
            None
        """
        pass

    @abstractmethod
    def stop(self, *args, **kwargs):
        """
        Stop a domain
        Returns:
            None
        """
        pass

    @abstractmethod
    def shutdown(self, *args, **kwargs):
        """
        Shutdown a domain
        Returns:
            None
        """
        pass

    @abstractmethod
    def reboot(self, *args, **kwargs):
        """
        Reboot a domain
        Returns:
            None
        """
        pass

    @abstractmethod
    def bootstrap(self, *args, **kwargs):
        """
        Does any actions needed to get the domain ready to be used, ran on
        prefix init.
        Return:
            None
        """
        pass

    @abstractmethod
    def state(self, *args, **kwargs):
        """
        Return the current state of the domain
        Returns:
            str: Small description of the current domain state
        """
        pass

    @abstractmethod
    def running(self, *args, **kwargs):
        """
        Returns:
            (bool): True if the VM is running
        """
        pass

    @abstractmethod
    def create_snapshot(self, name, *args, **kwargs):
        """
        Take any actions needed to create a snapshot
        Args:
            name(str): Name for the snapshot, will be used as key to retrieve
                it later
        Returns:
            None
        """
        pass

    @abstractmethod
    def revert_snapshot(self, name, *args, **kwargs):
        """
        Take any actions needed to revert/restore a snapshot
        Args:
            name(str): Name for the snapshot, same that was set on creation
        Returns:
            None
        """
        pass

    def export_disks(self, standalone, dst_dir, compress, *args, **kwargs):
        """
        Export 'disks' as a standalone image or a layered image.
        Args:
            disks(list): The names of the disks to export
              (None means all the disks)
            standalone(bool): If true create a copy of the layered image
              else create a new disk which is a combination of the current
              layer and the base disk.
            dst_dir (str): dir to place the exported images
            compress (bool): if true, compress the exported image.
        """
        pass

    def interactive_console(self):
        """
        Run an interactive console
        Returns:
            lago.utils.CommandStatus: resulf of the interactive execution
        """
        return self.vm.interactive_ssh()

    def extract_paths_dead(self, paths, ignore_nopath):
        """
        Extract the given paths from the domain, without the underlying OS
        awareness
        """
        pass

    def name(self):
        return self.vm.name()

    def extract_paths(self, paths, ignore_nopath):
        """
        Extract the given paths from the domain
        Args:
            paths(list of str): paths to extract
            ignore_nopath(boolean): if True will ignore none existing paths.
        Returns:
            None
        Raises:
            :exc:`~lago.plugins.vm.ExtractPathNoPathError`: if a none existing
                path was found on the VM, and ``ignore_nopath`` is True.
            :exc:`~lago.plugins.vm.ExtractPathError`: on all other failures.
        """
        try:
            if self._has_tar_and_gzip():
                self._extract_paths_tar_gz(paths, ignore_nopath)
            else:
                self._extract_paths_scp(paths, ignore_nopath)
        except (ssh.LagoSSHTimeoutException, LagoVMNotRunningError):
            raise ExtractPathError(
                'Unable to extract paths from {0}: unreachable with SSH'.
                format(self.vm.name())
            )

    @check_running
    def _has_tar_and_gzip(self):
        with self.vm._ssh() as client:
            _, stdout, _ = client.exec_command("ls /usr/bin/tar")
            if stdout.read().strip() != "/usr/bin/tar":
                return False
            _, stdout, _ = client.exec_command("ls /usr/bin/gzip")
            if stdout.read().strip() != "/usr/bin/gzip":
                return False
        return True

    @staticmethod
    def _prepare_tar_gz_command(remote_paths, compression_level):
        cmd = "tar --dereference -c {} | gzip -f -{}"
        remote_paths_arg = " ".join(remote_paths)
        return cmd.format(remote_paths_arg, compression_level)

    def _pipe_ssh_cmd_output_to_file(self, cmd, out_file):
        with self.vm._ssh() as client:
            _, stdout, _ = client.exec_command(cmd)
            out_file.write(stdout.read())
            out_file.flush()
            os.fsync(out_file.fileno())

    @contextlib.contextmanager
    def _tar_gz_archive_from(self, remote_paths, compression_level=5):
        with tempfile.NamedTemporaryFile() as archive_file:
            tar_gz_cmd = self._prepare_tar_gz_command(
                remote_paths, compression_level
            )
            self._pipe_ssh_cmd_output_to_file(tar_gz_cmd, archive_file)
            LOGGER.debug(
                "Created %s archive with collected paths", archive_file.name
            )
            yield archive_file

    @contextlib.contextmanager
    def _remote_paths_extracted_to_temp_dir(self, remote_paths):
        with self._tar_gz_archive_from(remote_paths) as archive_file:
            with utils.TemporaryDirectory() as tmpdir_path:
                LOGGER.debug(
                    "Extracting archive %s to temporary directory: %s",
                    archive_file.name, tmpdir_path
                )
                args = ["tar", "-xf", archive_file.name, "-C", tmpdir_path]
                cmd_status = utils.run_command(args)
                if cmd_status.code != 0:
                    LOGGER.error("'tar' command failed: %s", cmd_status.err)
                yield tmpdir_path

    @check_running
    def _extract_paths_tar_gz(self, paths, ignore_nopath):
        remote_paths = tuple(p[0] for p in paths)

        with self._remote_paths_extracted_to_temp_dir(
            remote_paths
        ) as tmpdir_path:
            for remote_path, desired_local_path in paths:
                LOGGER.debug(
                    'Moving %s to %s',
                    remote_path,
                    desired_local_path,
                )
                try:
                    # we need to strip first slash from absolute
                    # 'remote_path' to make 'os.path.join' work
                    current_local_path = os.path.join(
                        tmpdir_path, remote_path[1:]
                    )
                    shutil.move(current_local_path, desired_local_path)
                except IOError as e:
                    if e.errno == errno.ENOENT:
                        if ignore_nopath:
                            msg = (
                                '%s: ignoring since ignore_nopath '
                                'was set to True'
                            )
                            LOGGER.debug(msg, remote_path)
                        else:
                            raise ExtractPathNoPathError(remote_path)
                    else:
                        raise

    @check_running
    def _extract_paths_scp(self, paths, ignore_nopath):
        for host_path, guest_path in paths:
            LOGGER.debug(
                'Extracting scp://%s:%s to %s',
                self.vm.name(),
                host_path,
                guest_path,
            )
            try:
                self.vm.copy_from(
                    local_path=guest_path,
                    remote_path=host_path,
                    propagate_fail=not ignore_nopath
                )
            except ExtractPathNoPathError as err:
                if ignore_nopath:
                    LOGGER.debug(
                        '%s: ignoring since ignore_nopath was set to True',
                        err.args[0]
                    )
                else:
                    raise


class VMPlugin(plugins.Plugin):
    __metaclass__ = ABCMeta
    '''
    This class takes care of the high level abstraction for a VM (a domain in
    the initfile lingo). From starting/stopping it to loading and calling the
    provider if needed. If you want to change only the way the VM is
    provisioned you can take a look to the `class:VMProviderPlugin` instead.
    This base class includes also some basic methods implemented with ssh.
    VM properties:
    * name
    * cpus
    * memory
    * disks
    * metadata
    * network/mac addr
    * virt_env
    '''

    def __init__(self, env, spec):
        self.virt_env = env
        self._spec = self._normalize_spec(spec.copy())

        self._ssh_client = None
        self.service_providers = plugins.load_plugins(
            namespace=plugins.PLUGIN_ENTRY_POINTS['vm-service'],
            instantiate=False,
        )
        self._service_class = self._get_service_provider()
        self.vm_providers = plugins.load_plugins(
            namespace=plugins.PLUGIN_ENTRY_POINTS['vm-provider'],
            instantiate=False,
        )
        self.provider = self._get_vm_provider()

    def start(self, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.start(*args, **kwargs)

    def stop(self, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.stop(*args, **kwargs)

    def shutdown(self, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.shutdown(*args, **kwargs)

    def reboot(self, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.reboot(*args, **kwargs)

    def bootstrap(self, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.bootstrap(*args, **kwargs)

    def state(self, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.state(*args, **kwargs)

    def running(self, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.running(*args, **kwargs)

    def create_snapshot(self, name, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.create_snapshot(name, *args, **kwargs)

    def revert_snapshot(self, name, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.revert_snapshot(name, *args, **kwargs)

    def interactive_console(self, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.interactive_console(*args, **kwargs)

    def extract_paths(self, paths, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.extract_paths(paths, *args, **kwargs)

    def extract_paths_dead(self, paths, *args, **kwargs):
        """
        Thin method that just uses the provider
        """
        return self.provider.extract_paths_dead(paths, *args, **kwargs)

    def export_disks(
        self,
        standalone=True,
        dst_dir=None,
        compress=False,
        collect_only=False,
        with_threads=True,
        *args,
        **kwargs
    ):
        """
        Thin method that just uses the provider
        """
        return self.provider.export_disks(
            standalone, dst_dir, compress, collect_only, with_threads, *args,
            **kwargs
        )

    def copy_to(self, local_path, remote_path, recursive=True):
        with LogTask(
            'Copy %s to %s:%s' % (local_path, self.name(), remote_path),
        ):
            try:
                with self._scp() as scp:
                    scp.put(
                        files=local_path,
                        remote_path=remote_path,
                        recursive=recursive,
                    )
            except (OSError, SCPException) as err:
                raise LagoCopyFilesToVMError(local_path, str(err))

    def copy_from(
        self, remote_path, local_path, recursive=True, propagate_fail=True
    ):
        with LogTask(
            'Copy from %s:%s to %s' % (self.name(), remote_path, local_path),
            propagate_fail=propagate_fail
        ):
            try:
                with self._scp(propagate_fail=propagate_fail) as scp:
                    scp.get(
                        recursive=recursive,
                        remote_path=remote_path,
                        local_path=local_path,
                    )
            except SCPException as err:
                err_substr = ': No such file or directory'
                if all(
                    (
                        len(err.args) > 0,
                        isinstance(err.args[0], basestring),
                        err_substr in err.args[0],
                    )
                ):
                    raise ExtractPathNoPathError(err.args[0])
                else:
                    raise LagoCopyFilesFromVMError(
                        remote_path, local_path, err.args[0]
                    )

    @property
    def metadata(self):
        return self._spec['metadata'].copy()

    @property
    def disks(self):
        return self._spec['disks'][:]

    @property
    def spec(self):
        return deepcopy(self._spec)

    @property
    def mgmt_name(self):
        return self._spec.get('mgmt_net', None)

    @property
    def mgmt_net(self):
        return self.virt_env.get_net(name=self.mgmt_name)

    @property
    def vm_type(self):
        return self._spec['vm-type']

    @property
    def groups(self):
        """
        Returns:
            list of str: The names of the groups to which this vm belongs
                (as specified in the init file)
        """
        groups = self._spec.get('groups', [])
        if groups:
            return groups[:]
        else:
            return groups

    @property
    def cpu_vendor(self):
        return getattr(self.provider, 'cpu_vendor')

    @property
    def cpu_model(self):
        return getattr(self.provider, 'cpu_model')

    def name(self):
        return str(self._spec['name'])

    def iscsi_name(self):
        return 'iqn.2014-07.org.lago:%s' % self.name()

    def ip(self):
        res = self.mgmt_net.resolve(self.name())
        return res.encode('ascii', 'ignore')

    def all_ips(self):
        nets = {}
        ips = []
        nets = self.virt_env.get_nets()
        for net in nets.values():
            mapping = net.mapping()
            for hostname, ip in mapping.items():
                # hostname is <hostname>-<ifacename>
                if hostname.startswith(self.name() + "-"):
                    ips.append(str(ip))
        return ips

    def ips_in_net(self, net_name):
        ips = []
        net = self.virt_env.get_net(name=net_name)
        mapping = net.mapping()
        for hostname, ip in mapping.items():
            # hostname is <hostname>-<ifacename>
            if hostname.startswith(self.name() + "-"):
                ips.append(str(ip))
        return ips

    def ssh(
        self,
        command,
        data=None,
        show_output=True,
        propagate_fail=True,
        tries=None,
    ):
        if not self.running():
            raise RuntimeError('Attempt to ssh into a not running host')

        return ssh.ssh(
            ip_addr=self.ip(),
            host_name=self.name(),
            command=command,
            data=None,
            show_output=True,
            propagate_fail=True,
            tries=None,
            ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
            username=self._spec.get('ssh-user'),
            password=self._spec.get('ssh-password'),
        )

    def wait_for_ssh(self):
        return ssh.wait_for_ssh(
            ip_addr=self.ip(),
            host_name=self.name(),
            connect_timeout=self._spec.get('boot_time_sec', 600),
            ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
            username=self._spec.get('ssh-user'),
            password=self._spec.get('ssh-password'),
        )

    def ssh_script(self, path, show_output=True):
        return ssh.ssh_script(
            ip_addr=self.ip(),
            host_name=self.name(),
            ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
            path=path,
            show_output=show_output,
            username=self._spec.get('ssh-user'),
            password=self._spec.get('ssh-password'),
        )

    def ssh_reachable(self, tries=None, propagate_fail=True):
        """
        Check if the VM is reachable with ssh
        Args:
            tries(int): Number of tries to try connecting to the host
            propagate_fail(bool): If set to true, this event will appear
            in the log and fail the outter stage. Otherwise, it will be
            discarded.
        Returns:
            bool: True if the VM is reachable.
        """
        if not self.running():
            return False

        try:
            ssh.get_ssh_client(
                ip_addr=self.ip(),
                host_name=self.name(),
                ssh_tries=tries,
                propagate_fail=propagate_fail,
                ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
                username=self._spec.get('ssh-user'),
                password=self._spec.get('ssh-password'),
            )
        except ssh.LagoSSHTimeoutException:
            return False

        return True

    def save(self, path=None):
        if path is None:
            path = self.virt_env.virt_path('vm-%s' % self.name())

        dst_dir = os.path.dirname(path)
        if not os.path.exists(dst_dir):
            os.makedirs(dst_dir)

        with open(path, 'w') as f:
            utils.json_dump(self._spec, f)

    @check_running
    def service(self, name):
        if self._service_class is None:
            self._detect_service_provider()

        return self._service_class(self, name)

    @check_running
    def interactive_ssh(self, command=None):
        if command is None:
            command = ['bash']

        return ssh.interactive_ssh(
            ip_addr=self.ip(),
            host_name=self.name(),
            ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
            command=command,
            username=self._spec.get('ssh-user'),
            password=self._spec.get('ssh-password'),
        )

    def nics(self):
        return self._spec['nics'][:]

    def nets(self):
        return [nic['net'] for nic in self._spec['nics']]

    def distro(self):
        distro = self._spec.get('distro', None)
        if distro is None:
            distro = self._template_metadata().get('distro', None)

        return distro

    def root_password(self):
        root_password = self._spec.get('root-password', None)
        if root_password is None:
            root_password = self._spec.get('ssh-password', '')

        return root_password

    def collect_artifacts(self, host_path, ignore_nopath):
        self.extract_paths(
            [
                (
                    guest_path,
                    os.path.join(host_path, guest_path.replace('/', '_')),
                ) for guest_path in self._artifact_paths()
            ],
            ignore_nopath=ignore_nopath
        )

    def guest_agent(self):
        if 'guest-agent' not in self._spec:
            for possible_name in ('qemu-guest-agent', 'qemu-ga'):
                try:
                    if self.service(possible_name).exists():
                        self._spec['guest-agent'] = possible_name
                        self.save()
                        break
                except RuntimeError as err:
                    raise RuntimeError(
                        'Could not find guest agent service: %s' % err
                    )
            else:
                raise RuntimeError('Could not find guest agent service')

        return self.service(self._spec['guest-agent'])

    def has_guest_agent(self):
        try:
            self.guest_agent()
        except RuntimeError:
            return False

        return True

    def _get_vm_provider(self):
        default_provider = config.get('default_vm_provider')
        provider_name = self._spec.get('vm-provider', default_provider)
        provider = self.vm_providers.get(provider_name)
        self._spec['vm-provider'] = provider_name
        return provider(vm=self)

    @classmethod
    def _normalize_spec(cls, spec):
        spec['snapshots'] = spec.get('snapshots', {})
        spec['metadata'] = spec.get('metadata', {})

        if 'root-password' not in spec:
            root_password = config.get('root_password')
            if root_password:
                spec['ssh-password'] = root_password
            else:
                spec['ssh-password'] = config.get('ssh_password')

        if 'ssh-user' not in spec:
            spec['ssh-user'] = config.get('ssh_user')

        return spec

    @contextlib.contextmanager
    def _ssh(self, propagate_fail=True):
        client = ssh.get_ssh_client(
            propagate_fail=propagate_fail,
            ip_addr=self.ip(),
            host_name=self.name(),
            ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
            username=self._spec.get('ssh-user'),
            password=self._spec.get('ssh-password'),
        )
        try:
            yield client
        finally:
            client.close()

    @contextlib.contextmanager
    def _scp(self, propagate_fail=True):
        with self._ssh(propagate_fail) as ssh_client:
            scp = SCPClient(ssh_client.get_transport())
            yield scp

    def _detect_service_provider(self):
        LOGGER.debug('Detecting service provider for %s', self.name())

        for provider_name, service_class in self.service_providers.items():
            if service_class.is_supported(self):
                LOGGER.debug(
                    'Setting %s as service provider for %s',
                    provider_name,
                    self.name(),
                )
                self._service_class = service_class
                self._spec['service_provider'] = provider_name
                self.save()
                return

        raise RuntimeError('No service provider detected for %s' % self.name())

    def _template_metadata(self):
        return self._spec['disks'][0].get('metadata', {})

    def _artifact_paths(self):
        return self._spec.get('artifacts', [])

    def _get_service_provider(self):
        """
        **NOTE**: Can be reduced to just one get call once we remove support
        for the service_class spec entry
        Returns:
            class: class for the loaded provider for that vm_spec
            None: if no provider was specified in the vm_spec
        """
        service_class = self._spec.get('service_class', None)
        if service_class is not None:
            warnings.warn(
                'The service_class key for a domain is deprecated, you should '
                'change it to service_provider instead'
            )
            service_provider = _resolve_service_class(
                class_name=service_class,
                service_providers=self.service_providers,
            )
        else:
            service_provider = self.service_providers.get(
                self._spec.get('service_provider', None),
                None,
            )

        return service_provider


def _resolve_service_class(class_name, service_providers):
    """
    **NOTE**: This must be remved once the service_class spec entry is fully
    deprecated
    Retrieves a service plugin class from the class name instead of the
    provider name
    Args:
        class_name(str): Class name of the service plugin to retrieve
        service_providers(dict): provider_name->provider_class of the loaded
            service providers
    Returns:
        class: Class of the plugin that matches that name
    Raises:
        lago.plugins.NoSuchPluginError: if there was no service plugin that
            matched the search
    """
    for plugin in service_providers.itervalues():
        if plugin.__class__.__name__ == class_name:
            return plugin

    raise plugins.NoSuchPluginError(
        'No service provider plugin with class name %s found, loaded '
        'providers: %s' % (
            class_name,
            [
                plugin.__class__.__name__
                for plugin in service_providers.itervalues()
            ],
        )
    )
