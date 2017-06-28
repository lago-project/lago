##########################
LagoInitFile Specification
##########################

Note: this is work under progress, if you'd like to contribute to the
documentation, please feel free to open a PR. In the meanwhile, we recommend
looking at LagoInitFile examples available at:

https://github.com/lago-project/lago-examples/tree/master/init-files

Each environment in Lago is created from an init file, the recommended format
is YAML, although at the moment of writing JSON is still supported. By default,
Lago will look for a file named ``LagoInitFile`` in the directory it was
triggered. However you can pick a different file by running::

    $ lago init <FILENAME>


Sections
========
The init file is composed out of two major sections: domains, and nets.
Each virtual machine you wish to create needs to be under the ``domains``
section. ``nets`` will define the network topology, and when you add a
nic to a domain, it must be defined in the ``nets`` section.


Example:

.. code-block:: yaml

    domains:
      vm-el73:
        memory: 2048
        service_provider: systemd
        nics:
          - net: lago
        disks:
          - template_name: el7.3-base
             type: template
             name: root
             dev: vda
             format: qcow2
        artifacts:
          - /var/log
    nets:
      lago:
        type: nat
        dhcp:
          start: 100
          end: 254
        management: true
        dns_domain_name: lago.local

domains
-------

``<name>``: The name of the virtual machine.

    memory(int)
       The virtual machine memory in GBs.
    vcpu(int)
        Number of virtual CPUs.
    service_provider(string)
       This will instruct which service provider to use when enabling services
       in the VM by  calling :func:`lago.plugins.vm.VMPlugin.service`,
       Possible values: `systemd, sysvinit`.
    cpu_model(string)
        CPU Family to emulate for the virtual machine. The list of supported
        types depends on your hardware and the libvirtd version you use,
        to list them you can run locally:

        .. code-block:: bash

            $ virsh cpu-models x86_64

    cpu_custom(dict)
        This allows more fine-grained control of the CPU type,
        see CPU_ section for details.
    nics(list)
        Network interfaces. Each network interface must be defined in the
        global `nets` section. By default each nic will be assigned an IP
        according to the network definition. However, you may also use
        static IPs here, by writing:

        .. code-block:: yaml

            nics:
                - net: net-01
                  ip:  192.168.220.2

        The same network can be declared multiple times for each domain.

    disks(list)
        type
            Disk type, possible values:

            template
                A Lago template, this would normally the bootable device.
            file
                A local disk image. Lago will thinly provision it during init
                stage, this device will not be bootable. But can obviously
                be used for additional storage.
        template_name(string)
            Applies only to disks of type ``template``. This should be one
            of the available Lago templates, see Templates_ section for
            the list.
        size(string)
            Disk size to thinly provision in GB. This is only supported in
            ``file`` disks.

        format(string)
            *TO-DO: no docs yet..*
        device(string)
            Linux device: vda, sdb, etc. Using a device named "sd*" will use
            virtio-scsi.
        build(list)
          This section should describe how to build/configure VMs.
          The build/configure action will happen during ``init``.

            virt-customize(dict)
                Instructions to pass to `virt-customize`_, where the key is the name
                of the option and the value is the arguments for that option.

                This operation is only supported on disks which contains OS.

                A special instruction is ``ssh-inject: ''``
                Which will ensure Lago's generated SSH keys will be injected
                into the VM. This is useful when you don't want to run the
                bootstrap stage.

                For example:

                .. code-block:: yaml

                    - template_name: el7.3-base
                      build:
                          - virt-customize:
                                ssh-inject: ''
                                touch: [/root/file1, /root/file2]

                See `build`_ section for details.

    artifacts(list)
        Paths on the VM that Lago should collect when using `lago collect`
        from the CLI, or :func:`~lago.prefix.Prefix.collect_artifacts` from
        the SDK.
    groups(list)
        Groups this VM belongs to. This is most usefull when deploying the VM
        with Ansible.
    bootstrap(bool)
        Whether to run bootstrap stage on the VM's template disk, defaults
        to True.
    ssh-user(string)
        SSH user to use and configure, defaults to `root`
    vm-provider(string)
        VM Provider plugin to use, defaults to `local-libvirt`.
    vm-type(string)
        VM Plugin to use. A custom VM Plugin can be passed here,
        note that it needs to be available in your Python Entry points.
        See lago-ost-plugin_ for an example.
    metadata(dict)
        *TO-DO: no docs yet..*


nets
----
``<name>``: The name of the network, should be an alphanumeric string.
            Currently we do not enforce that it is only alphanumeric,
            but we might do so in the future.

    type(string)
        Type of the network. May be `nat` or `bridge`.



.. _Templates: Templates.html
.. _`virt-customize`: http://libguestfs.org/virt-customize.1.html
.. _lago-ost-plugin: https://github.com/lago-project/lago-ost-plugin/blob/master/setup.cfg
.. _CPU: CPU.html
.. _build: BUILD.html
