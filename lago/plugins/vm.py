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
import contextlib
import functools
import logging
import os
import warnings
from abc import (ABCMeta, abstractmethod)

from scp import SCPClient

from .. import (config, utils, log_utils, plugins, ssh, )

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)


class VMErrror(Exception):
    pass


class ExtractPathError(VMErrror):
    pass


def _check_alive(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if not self.alive():
            raise RuntimeError('VM %s is not running' % self.name())
        return func(self, *args, **kwargs)

    return wrapper


class VMProviderPlugin(plugins.Plugin):
    """
    If you want to use a custom provider for you VMs (say, ovirt for example),
    you have to inherit from this class, and then define the
    'default_vm_provider' in your config to be your plugin, or explicitly
    specify it on each domain definition in the initfile with 'vm_provider' key
    """

    def __init__(self, vm):
        self.vm = vm

    @abstractmethod
    def start(self, *args, **kwargs):
        pass

    @abstractmethod
    def stop(self, *args, **kwargs):
        pass

    @abstractmethod
    def defined(self, *args, **kwargs):
        pass

    @abstractmethod
    def bootstrap(self, *args, **kwargs):
        pass

    @abstractmethod
    def state(self, *args, **kwargs):
        pass

    @abstractmethod
    def create_snapshot(self, name, *args, **kwargs):
        pass

    @abstractmethod
    def revert_snapshot(self, name, *args, **kwargs):
        pass

    @abstractmethod
    def vnc_port(self, *args, **kwargs):
        pass

    def interactive_console(self):
        return self.vm.interactive_ssh()

    def extract_paths(self, paths):
        if self.vm.alive() and self.vm.ssh_reachable():
            self._extract_paths_scp(paths=paths)
        elif self.vm.alive():
            raise ExtractPathError(
                'Unable to extract logs from alive but unreachable host %s. '
                'Try stopping it first' % self.vm.name()
            )
        else:
            raise ExtractPathError(
                'Unable to extract logs from alive but unreachable host %s. '
                'Try stopping it first' % self.vm.name()
            )

    def _extract_paths_scp(self, paths):
        for host_path, guest_path in paths:
            LOGGER.debug(
                'Extracting scp://%s:%s to %s',
                self.vm.name(),
                host_path,
                guest_path,
            )
            self.vm.copy_from(local_path=guest_path, remote_path=host_path)


class VMPlugin(plugins.Plugin):
    __metaclass__ = ABCMeta
    '''VM properties:
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
        return self.provider.start(*args, **kwargs)

    def stop(self, *args, **kwargs):
        return self.provider.stop(*args, **kwargs)

    def defined(self, *args, **kwargs):
        return self.provider.defined(*args, **kwargs)

    def bootstrap(self, *args, **kwargs):
        return self.provider.bootstrap(*args, **kwargs)

    def state(self, *args, **kwargs):
        return self.provider.state(*args, **kwargs)

    def create_snapshot(self, name, *args, **kwargs):
        return self.provider.create_snapshot(name, *args, **kwargs)

    def revert_snapshot(self, name, *args, **kwargs):
        return self.provider.revert_snapshot(name, *args, **kwargs)

    def interactive_console(self, *args, **kwargs):
        return self.provider.interactive_console(*args, **kwargs)

    def vnc_port(self, *args, **kwargs):
        return self.provider.vnc_port(*args, **kwargs)

    def extract_paths(self, paths, *args, **kwargs):
        return self.provider.extract_paths(paths, *args, **kwargs)

    def copy_to(self, local_path, remote_path):
        with LogTask(
            'Copy %s to %s:%s' % (local_path, self.name(), remote_path),
        ):
            with self._scp() as scp:
                scp.put(local_path, remote_path)

    def copy_from(self, remote_path, local_path, recursive=True):
        with self._scp() as scp:
            scp.get(
                recursive=recursive,
                remote_path=remote_path,
                local_path=local_path,
            )

    @property
    def metadata(self):
        return self._spec['metadata'].copy()

    def name(self):
        return str(self._spec['name'])

    def iscsi_name(self):
        return 'iqn.2014-07.org.lago:%s' % self.name()

    def ip(self):
        return str(self.virt_env.get_net().resolve(self.name()))

    def ssh(
        self,
        command,
        data=None,
        show_output=True,
        propagate_fail=True,
        tries=None,
    ):
        if not self.alive():
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
        )

    def wait_for_ssh(self):
        return ssh.wait_for_ssh(
            ip_addr=self.ip(),
            host_name=self.name(),
            connect_retries=self._spec.get('boot_time_sec', 50),
            ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
        )

    def ssh_script(self, path, show_output=True):
        return ssh.ssh_script(
            ip_addr=self.ip(),
            host_name=self.name(),
            ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
            path=path,
            show_output=show_output,
        )

    def alive(self):
        return self.state() == 'running'

    def ssh_reachable(self):
        try:
            ssh.get_ssh_client(
                ip_addr=self.ip(),
                host_name=self.name(),
                ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
            )
        except RuntimeError:
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

    @_check_alive
    def service(self, name):
        if self._service_class is None:
            self._detect_service_provider()

        return self._service_class(self, name)

    @_check_alive
    def interactive_ssh(self, command=None):
        if command is None:
            command = ['bash']

        return ssh.interactive_ssh(
            ip_addr=self.ip(),
            host_name=self.name(),
            ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
            command=command,
        )

    def nics(self):
        return self._spec['nics'][:]

    def nets(self):
        return [nic['net'] for nic in self._spec['nics']]

    def distro(self):
        return self._template_metadata().get('distro', None)

    def root_password(self):
        return self._spec['root-password']

    def collect_artifacts(self, host_path):
        self.extract_paths(
            [
                (
                    guest_path,
                    os.path.join(host_path, guest_path.replace('/', '_')),
                ) for guest_path in self._artifact_paths()
            ]
        )

    def guest_agent(self):
        if 'guest-agent' not in self._spec:
            for possible_name in ('qemu-ga', 'qemu-guest-agent'):
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
            spec['root-password'] = config.get('default_root_password')

        return spec

    @contextlib.contextmanager
    def _scp(self):
        client = ssh.get_ssh_client(
            ip_addr=self.ip(),
            host_name=self.name(),
            ssh_key=self.virt_env.prefix.paths.ssh_id_rsa(),
        )
        scp = SCPClient(client.get_transport())
        try:
            yield scp
        finally:
            client.close()

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
