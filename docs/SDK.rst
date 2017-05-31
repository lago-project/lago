########
Lago SDK
########
The SDK goal is to automate the creation of virtual environments, by using
Lago directly from Python. Currently, most CLI operations are supported from
the SDK, though not all of them(specifically, snapshot and export).


Starting an enviornment from the SDK
====================================

Prerequirements
---------------

1. Have Lago installed, see the  `installation notes`_.

2. Create a ``LagoInitFile``, check out `LagoInitFile syntax`_ for more details.


Prepare the enviornment
-----------------------
*Note*: This example is available as a Jupyter notebook `here`_ or converted to
`reST here`_.

Assuming the ``LagoInitFile`` is saved in ``/tmp/el7-init.yaml`` and contains:

.. code:: yaml

    domains:
      vm01:
        memory: 1024
        nics:
          - net: lago
        disks:
          - template_name: el7.3-base
            type: template
            name: root
            dev: sda
            format: qcow2
    nets:
      lago:
        type: nat
        dhcp:
          start: 100
          end: 254

Which is a simple setup, containing one CentOS 7.3 virtual machine and
one management network. Then you start the environment by running:

.. code:: python

   import logging
   from lago import sdk

   env = sdk.init(config='/tmp/el7-init.yaml',
                  workdir='/tmp/my_test_env',
                  logfile='/tmp/lago.log',
                  loglevel=logging.DEBUG)

Where:
    1. ``config`` is the path to a valid init file, in YAML format.
    2. ``workdir`` is the place Lago will use to save the images and metadata.
    3. The ``logfile`` and ``loglevel`` parameters add a FileHandler to
       Lago's root logger.

Note that if this is the first time you are running Lago it will first
download the template(in this example ``el7-base``), which might take a
while [1]_. You can follow up the progress by watching the log file, or
alternatively if working in an interactive session, by running:

.. code:: python

   from lago import sdk
   sdk.add_stream_logger()

Which will print all the Lago operations to stdout.

Starting the enviornment
------------------------

Once :func:`~lago.sdk.init` method returns, the environment is ready to be
started, taking up from the last example, executing:

.. code:: python

   env.start()

Would start the VMs specified in the init file, and make them available(among
others) through SSH:

.. code:: python

   >>> vm = env.get_vms()['vm01']
   >>> vm.ssh(['hostname', '-f'])
   CommandStatus(code=0, out='vm01.lago.local\n', err='')

You can also run an interactive SSH session:

.. code:: python

  >>> res = vm.interactive_ssh()
  [root@vm01 ~]# ls -lsah
  total 20K
  0 dr-xr-x---.  3 root root 103 May 28 03:11 .
  0 dr-xr-xr-x. 17 root root 224 Dec 12 17:00 ..
  4.0K -rw-r--r--.  1 root root  18 Dec 28  2013 .bash_logout
  4.0K -rw-r--r--.  1 root root 176 Dec 28  2013 .bash_profile
  4.0K -rw-r--r--.  1 root root 176 Dec 28  2013 .bashrc
  4.0K -rw-r--r--.  1 root root 100 Dec 28  2013 .cshrc
  0 drwx------.  2 root root  29 May 28 03:11 .ssh
  4.0K -rw-r--r--.  1 root root 129 Dec 28  2013 .tcshrc
  [root@vm01 ~]# exit
  exit
  >>> res.code
  0



Controlling the environment
----------------------------

You can start or stop the environment by calling
:func:`~lago.prefix.Prefix.start` and :func:`~lago.prefix.Prefix.stop`, finally
you can destroy the environment with :func:`lago.sdk.SDK.destroy` method,
note that it will stop all VMs, and remove the provided working directory.

.. code:: python

   >>> env.destroy()
   >>>



Disk consumption for the workdir
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generally speaking, the workdir disk consumption depends on which operation
you run inside the underlying VMs. Lago uses QCOW2 layered images by default,
so that each environment you create, sets up its own layer on top of the
original template Lago downloaded the first time ``init`` was ran with that
specific template. So when the VM starts, it usually consumes less than 30MB.
As you do more operations - the size might increase, as your current image
diverges from the original template. For more information see qemu-img_



Differences from the CLI
========================

1. Creating Different ``prefixes`` inside the workdir is not supported. In the
   CLI, you can have several prefixes inside a ``workdir``. The reasoning
   behind that is that when working from Python, you can manage the
   environment directly by your own(using a temporary or fixed path).

2. Logging - In the CLI, all log operations are kept in the current ``prefix``
   under `logs/lago.log` path. The SDK keeps that convention, but allows you
   to add additional log files by passing log filename and level parameters to
   :func:`~lago.sdk.init` command. Additionally, you can work in debug mode, by
   logging all commands to stdout and stderr, calling the module-level method
   :func:`~lago.sdk.add_stream_logger`. Note that this will log everything
   for all environments.

3. :class:`~lago.prefix.Prefix` class. This is more of an implementation
   issue: the core per-environment operations are exposed both for the CLI and
   SDK in that class. In order to provide consistency and ease of use
   for the SDK, only the methods which make sense for SDK usage are exposed
   in the SDK, the CLI does not require that, as the methods aren't exposed
   at all(only verbs in :class:`~lago.cmd.py`.



.. _`installation notes`: Installation.html
.. _`LagoInitFile syntax`: LagoInitFile.html
.. [1] On a normal setup, where the templates are already downloaded, the ``init`` stage should take less than a minute(but probably at least 15 seconds).
.. _qemu-img: https://linux.die.net/man/1/qemu-img
.. _here: https://github.com/lago-project/lago/tree/master/docs/examples/lago_sdk_one_vm_one_net.ipynb
.. _`reST here`: examples/lago_sdk_one_vm_one_net.html
