###############
Installing Lago
###############

Lago is officially supported and tested on Fedora 24+ and CentOS 7.3
distributions. However, it should be fairly easy to get it running on
debian variants.

As Lago requires libvirtd installed and several group permissions,
it cannot be installed solely via ``pip``. For that reason the
recommended method of installation is using the RPM. The easiest way, is
to use the `Install script`_ which we test and verify regularly [2]_.


pip
===

1. Install system package dependencies, this may vary according to your
   distribution:

   A. CentOS 7.3+

   .. code:: bash

        $ yum install -y epel-release centos-release-qemu-ev
        $ yum install -y libvirt libvirt-devel libguestfs-tools \
            libguestfs-devel gcc libffi-devel openssl-devel \
            qemu-kvm-ev


   B. Fedora 24+

   .. code:: bash

       $ yum install -y libvirt libvirt-devel libguestfs-tools \
           libguestfs-devel gcc libffi-devel openssl-devel qemu-kvm

   C. Debian / Ubuntu - *TO-DO*
   D. ArchLinux - *TO-DO*

2. Install libguestfs Python bindings, as they are not available on PyPI [3]_:

   .. code:: bash

       $ pip install http://download.libguestfs.org/python/guestfs-1.36.4.tar.gz


3. Install Lago with pip:

   .. code:: bash

       $ pip install lago


4. Setup permissions(replacing USERNAME accordingly):

   .. code:: bash

       $ sudo usermod -a -G qemu,libvirt USERNAME
       $ sudo usermod -a -G USERNAME qemu
       $ chmod g+x $HOME

5. Create a global share for Lago to store templates:

   .. code:: bash

       $ sudo mkdir -p /var/lib/lago
       $ sudo mkdir -p /var/lib/lago/{repos,store,subnets}
       $ sudo chown -R USERNAME:USERNAME /var/lib/lago


   *Note:* if you don't want to share the templates between users, have a look
   at the Configuration_ section, and change ``lease_dir``, ``template_repos``
   and ``template_store`` accordingly.

6. Restart libvirt(if you have systemd, otherwise use your distribution
   specific tool):

   .. code:: bash

       $ systemctl restart libvirtd

7. Log out and login again


Fedora 24+ / CentOS 7.3
=======================

.. _`Install script`:

Install script
---------------

1. Download the installation script and make it executable:

   .. code:: bash

      $ curl https://raw.githubusercontent.com/lago-project/lago-demo/master/install_scripts/install_lago.sh \
          -o install_lago.sh \
          && chmod +x install_lago.sh


2. Run the installation script(replacing ``username`` with your username):

   .. code:: bash

       $ sudo ./install_lago.sh --user [username]


3. Log out and login again.

That's it! Lago should be installed.


Manual installation
-------------------


1. Add the following repository to a new file at
   ``/etc/yum.repos.d/lago.repo``:

   For Fedora:

   .. code:: bash

     [lago]
     baseurl=http://resources.ovirt.org/repos/lago/stable/0.0/rpm/fc$releasever
     name=Lago
     enabled=1
     gpgcheck=0

   For CentOS:

   .. code:: bash

     [lago]
     baseurl=http://resources.ovirt.org/repos/lago/stable/0.0/rpm/el$releasever
     name=Lago
     enabled=1
     gpgcheck=0


   *For CentOS only*, you need **EPEL** and **centos-release-qemu-ev**
   repositories, those can be installed by running:

       .. code:: bash

           $ sudo yum install -y epel-release centos-release-qemu-ev


   .. todo:: point to the release rpm once it's implemented, and use gpgcheck=1


2. With the Lago repository configured, run(for Fedora use ``dnf`` instead):

   .. code:: bash

       $ sudo yum install -y lago


3. Setup group permissions:

   .. code:: bash

       $ sudo usermod -a -G lago USERNAME
       $ sudo usermod -a -G qemu USERNAME
       $ sudo usermod -a -G USERNAME qemu


4. Add group execution rights to your home directory: [1]_

   .. code:: bash

       $ chmod g+x $HOME

5. Restart libvirtd:

   .. code:: bash

       $ sudo systemctl enable libvirtd
       $ sudo systemctl restart libvirtd

6. Log out and login again.



FAQ
===

* *Q*: After using the install script, how do I fix the permissions for
  another username?

  *A*: Run:

         .. code:: bash

             $ ./install_lago.sh -p --user [new_user]


* *Q*: Can Lago be installed in a Python virtualenv?

  *A*: Follow the same procedure as in the pip_ instructions, only run the
       pip installation under your virtualenv. Consult [3]_ if you want
       to install libguestfs Python bindings not from pip.


Troubleshooting
================

* *Problem*: QEMU throws an error it can't access files in my home directory.

  *Solution*: Check again that you have setup the permissions described in the
  `Manual Installation`_ section. After doing that, log out and log in again.
  If QEMU has the proper permissions, the following command should work(
  replace ``some/nested/path`` with a directory inside your home directory):

  .. code:: bash

      $ sudo -u qemu ls $HOME/some/nested/path


.. [1] For more information why this step is needed see
       https://libvirt.org/drvqemu.html, at the bottom of
       "POSIX users/groups" section.
.. [2] If the installation script does not work for you on the supported
       distributions, please open an issue at h
       ttps://github.com/lago-project/lago-demo.git
.. [3] libguestfs Python bindings is unfortunately not available on PyPI,
       see https://bugzilla.redhat.com/show_bug.cgi?id=1075594 for current
       status. You may also use the system-wide package, if those are
       available for your distribution. In that case, if using a virtualenv,
       ensure you are creating it with '--system-site-packages' option.
       For Fedora/CentOS the package is named `python2-libguestfs`, and for
       Debian `python-guestfs`.

.. _Configuration: Configuration.html
