"""
repo plugins
============
Common interface for managing vm's repos with Lago

"""

from abc import ABCMeta, abstractmethod
from lago.plugins import Plugin, NoSuchPluginError
import lago
import lago.utils as utils
import re

REPO_PLUGINS = {}
DISTRO_TO_PKG_MANAGER = {'el': 'yum', 'fc': 'dnf'}


def get_cls_by_distro(distro):
    global REPO_PLUGINS
    if not REPO_PLUGINS:
        REPO_PLUGINS = lago.plugins.load_plugins(
            'lago.plugins.repo', instantiate=False
        )

    for candidate_distro, pkg_manager in DISTRO_TO_PKG_MANAGER.viewitems():
        pattern = r'^' + candidate_distro + r'[0-9]*$'
        if re.match(pattern, distro):
            return REPO_PLUGINS[DISTRO_TO_PKG_MANAGER[candidate_distro]]

    raise NoSuchPluginError(
        'Repo plugin for distro {} does not exist'.format(distro)
    )


def get_cls(pkg_manger):
    if pkg_manger not in REPO_PLUGINS:
        raise NoSuchPluginError(pkg_manger)

    return REPO_PLUGINS[pkg_manger]


class RepoPlugin(Plugin):
    __metaclass__ = ABCMeta

    def __init__(self, vm):
        """
        Base class for repo plugins

        Args:
            vm(lago.plugins.VMPlugin): vm to wrap

        Returns:
            None
        """
        self.vm = vm
        self.mgmt_nets = vm.mgmt_nets()

    @abstractmethod
    def inject(self, *args, **kwargs):
        raise NotImplemented

    @abstractmethod
    def add(self, *args, **kwargs):
        raise NotImplemented

    @abstractmethod
    def inject_local_repo(self, *args, **kwargs):
        raise NotImplemented

    @abstractmethod
    def add_local_repo(self, *args, **kwargs):
        raise NotImplemented


class RepoPluginUserError(utils.LagoUserException):
    pass
