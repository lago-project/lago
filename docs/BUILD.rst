##########
Lago build
##########

Lago allows to build / configure VM disks during init stage.
In the init file, the key ``build`` should be added to each disk that needs to be configured.

``build`` should map to a list of Builders, where each builder in the list is
a one entry dictionary that maps to a dictionary that holds the options for that builder.

Options are key-value pairs, where the key is the name of the option
(without leading dashes), and the value is the argument for that option.
If the option takes no arguments, the empty string should be set as the value.
If the builder allows specifying an options multiple times, the value should
be a list of arguments.

*Note*: The build process runs "behind-the-back" of the OS (Before the VM starts), thus
should be used with care.

Builders
===========

Builders are commands that can be used to build/configure VMs.
Builders are called by the order they appear in the init file.

virt-customize
---------------
A tool for customizing a virtual machine (install packages, copying files, etc...).
`virt-customize` is part of the `libguestfs` tool set which is part of Lago's dependencies.

`virt-customize` can be called only on disks which contains an OS.

Depends on the version of `virt-customize` installed on your system (it can vary between
different OS), all the valid options for `virt-customize` can be specified in the init file.
For the full list of options please refer to `virt-customize documentation`_.

There is a special case when using `virt-customize` to inject ssh keys. If the
empty string is provided to ``ssh-inject`` option, Lago will replace it with
the path to lago's self generated ssh keys.

.. _`virt-customize documentation`: http://libguestfs.org/virt-customize.1.html

*Note*: If SELinux is enabled in a VM, it's possible that ``selinux-relabel``
will be required after adding / modifiyng its files.

Relation to bootstrap
======================
Configuration is taking place after Lago runs bootstrap.
You can disable bootstrap to all VMs by passing ``--skip-bootstrap`` to
``lago init``, or by adding ``bootstrap: false`` to the VM definition in
the init file (the second allows to control bootstrap per VM).

Since bootstrap is injecting ssh keys to the VMs, If skipping it,
it's recommended to inject the ssh keys using `virt-customize` builder
otherwise, shell access to the VM will use password authentication
(more details can be found in the Builders sections in this documents).

Example
========
In the following example, `virt-customize` builder will be called on the disk of vm01.

The changes will be:

- Injecting lago's self generated ssh keys.
- Copy ``dummy_file`` from the host to ``/root`` in ``vm01``
- Create files ``/root/file1`` and ``/root/file2`` in ``vm01``
- Finish with SELinux relabel of ``vm01``.

.. code:: yaml

    domains:
      vm01:
        artifacts: [/var/log]
        bootstrap: false
        disks:
        - build:
          - virt-customize:
              ssh-inject: ''
              copy: dummy_file:/root
              touch: [/root/file1, /root/file2]
              selinux-relabel: ''
          dev: vda
          format: qcow2
          name: root
          path: $LAGO_INITFILE_PATH/lago-basic-suite-4-1-engine_root.qcow2
          template_name: el7.3-base
          template_type: qcow2
          type: template
