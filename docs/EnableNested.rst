Virtualization and nested virtualization support
==================================================

In order to use Lago with nested virtualizaion you'll need to to the following:

#. Make sure that virtualization extension is enabled on the CPU, otherwise,
   you might need to enable it in the BIOS. Generally, if virtualization extension
   is disabled, `dmesg` log would contain a line similar to::

    kvm: disabled by BIOS

   **NOTE**: you can wait until everyithing is setup to reboot and change the
   bios, to make sure that everyithing will persist after reboot

#. To make sure that nested virtualization is enabled, run::

    $ cat /sys/module/kvm_intel/parameters/nested

   This command should print `Y` if nested virtualization is enabled, otherwise,
   enable it the following way:

#. Edit `/etc/modprobe.d/kvm-intel.conf` and add the following line::

    options kvm-intel nested=y

#. Reboot, and make sure nested virtualization is enabled.
