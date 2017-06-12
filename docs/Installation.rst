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
       $ sudo usermod -a -g USERNAME qemu


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
