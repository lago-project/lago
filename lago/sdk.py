from __future__ import print_function
from future.builtins import super
from lago import cmd
from lago.config import config as lago_config
from lago.lago_ansible import LagoAnsible
from lago import workdir as lago_workdir
from lago.log_utils import get_default_log_formatter
from sdk_utils import SDKWrapper, setup_sdk_logging
import weakref
import os
import logging


def add_stream_logger(level=logging.DEBUG, name=None):
    """
    Add a stream logger. This can be used for printing all SDK calls to stdout
    while working in an interactive session. Note this is a logger for the
    entire module, which will apply to all environments started in the same
    session. If you need a specific logger pass a ``logfile`` to
    :func:`~sdk.init`

    Args:
        level(int): :mod:`logging` log level
        name(str): logger name, will default to the root logger.

    Returns:
        None
    """

    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler()
    handler.setFormatter(get_default_log_formatter())
    handler.setLevel(level)
    logger.addHandler(handler)


def init(config, workdir=None, logfile=None, loglevel=logging.INFO, **kwargs):
    """
    Initialize the Lago environment

    Args:
        config(str): Path to LagoInitFile
        workdir(str): Path to initalize the workdir, defaults to "$PWD/.lago"
        **kwargs(dict): Pass arguments to :func:`~lago.cmd.do_init`
        logfile(str): A path to setup a log file.
        loglevel(int): :mod:`logging` log level.

    Returns:
        :class:`~lago.sdk.SDK`: Initialized Lago enviornment

    Raises:
       :exc:`~lago.utils.LagoException`: If initialization failed
    """

    setup_sdk_logging(logfile, loglevel)
    defaults = lago_config.get_section('init')
    if workdir is None:
        workdir = os.path.abspath('.lago')
    defaults['workdir'] = workdir
    defaults['virt_config'] = config
    defaults.update(kwargs)
    workdir, prefix = cmd.do_init(**defaults)
    return SDK(workdir, prefix)


def load_env(workdir, logfile=None, loglevel=logging.INFO):
    """
    Load an existing Lago environment

    Args:
        workdir(str): Path to the workdir directory, as created by
        :func:`~lago.sdk.init` or created by the CLI.
        logfile(str): A Path to setup a log file.
        loglevel(int): :mod:`logging` log level.

    Returns:
        :class:`~lago.sdk.SDK`: Initialized Lago environment

    Raises:
       :exc:`~lago.utils.LagoException`: If loading the environment failed.
    """

    setup_sdk_logging(logfile, loglevel)
    workdir = os.path.abspath(workdir)
    loaded_workdir = lago_workdir.Workdir(path=workdir)
    prefix = loaded_workdir.get_prefix('current')
    return SDK(loaded_workdir, prefix)


class SDK(object):
    """
    The SDK can be initialized in 3 ways:

        1. (Preferred) - by calling :func:`sdk.init`.
        2. By loading an existing workdir from the disk, with
            :func:`~load_env`.
        3. By passing already created workdir and prefix objects.
    """

    def __init__(self, workdir, prefix):
        """
        __init__

        Args:
            workdir(:class:`~lago.workdir.Workdir`): The enviornment
                workdir.
            prefix(:class:~lago.prefix.Prefix): The enviornment Prefix.

        Returns:
            None
        """

        self._workdir = workdir
        self._prefix = prefix
        # Proxy object to the prefix to expose
        self._pprefix = SDKWrapper(weakref.proxy(self._prefix))

    def __getattr__(self, name):
        try:
            attr = super().__getattr__(name)
        except AttributeError:
            attr = getattr(self._pprefix, name)
        return attr

    def __dir__(self):
        # For auto-complete to work, we need to return the methods of the proxy
        # object as well, which we return in __getattr__.
        # As we cannot call self.__dir__, we need to construct 'self's
        # attributes.
        return sorted(
            set(dir(type(self)) + list(self.__dict__) + dir(self._pprefix))
        )

    def destroy(self):
        """
        Destroy the environment, this will terminate all resources, and remove
        entirely the Lago working directory.
        """
        self._workdir.destroy()

    def ansible_inventory_temp_file(
        self, keys=['vm-type', 'groups', 'vm-provider']
    ):
        """
        Context manager which returns Ansible inventory written on a tempfile.
        This is the same as :func:`~ansible_inventory`, only the inventory file
        is written to a tempfile.

        Args:
            keys (list of str): Path to the keys that will be used to
                create groups.

        Yields:
            tempfile.NamedTemporaryFile: Temp file containing the inventory
        """
        lansible = LagoAnsible(self._prefix)
        return lansible.get_inventory_temp_file(keys=keys)

    def ansible_inventory(
        self,
        keys=['vm-type', 'groups', 'vm-provider'],
    ):
        """
        Get an Ansible inventory as a string, ``keys`` should be list on which
        to group the hosts by. You can use any key defined in LagoInitFile.

        Examples of possible `keys`:

            `keys=['disks/0/metadata/arch']`, would group the hosts by the
            architecture.

            `keys=['/disks/0/metadata/distro', 'disks/0/metadata/arch']`,
                would create groups by architecture and also by distro.

            `keys=['groups']` - would group hosts by the groups defined for
                each VM in the LagoInitFile, i.e.:

                    domains:

                        vm-01:
                            ...
                            groups: web-server
                            ..
                        vm-02:
                            ..
                            groups: db-server


        Args:
            keys (list of str): Path to the keys that will be used to
                create groups.

        Returns:
            str: INI-like Ansible inventory
        """

        lansible = LagoAnsible(self._prefix)
        return lansible.get_inventory_str(keys=keys)
