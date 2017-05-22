from __future__ import print_function
from lago import cmd
from sdk_utils import SDKWrapper


def init(config, workdir=None, **kwargs):
    """
    Initialize the Lago environment

    Args:
        config(str): Path to LagoInitFile
        workdir(str): Path to initalize the workdir
        **kwargs(dict): Pass arguments to :func:`~lago.cmd.do_init`

    Returns:
        :class:`~lago.sdk.SDK`: Initialized Lago enviornment

    Raises:
       :exc:`~lago.utils.LagoException`: If initialization failed
    """

    # .. to-do:: load global configuration from a file
    # .. to-do:: allow loading the env from an existing directory
    defaults = {
        'workdir': workdir,
        'template_repo_path': 'http://templates.ovirt.org/repo/repo.metadata',
        'template_store': '/var/lib/lago/store',
        'template_repos': '/var/lib/lago/repos',
        'set_current': True,
        'skip_bootstrap': False,
        'skip_build': False,
        'prefix_name': 'default',
    }
    defaults.update(kwargs)
    defaults['virt_config'] = config
    workdir, prefix = cmd.do_init(**defaults)
    return SDK(workdir, prefix)


class SDK(object):
    """
    The SDK can be initialized in 2 ways:
    1. (Preferred) - by calling :func:`sdk.init`.
    2. By passing already created workdir and prefix objects.
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
        self._pprefix = SDKWrapper(self._prefix)

    def __getattr__(self, name):
        try:
            attr = super(SDK, self).__getattr__(name)
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
