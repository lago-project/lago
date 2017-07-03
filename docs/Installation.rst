###############
Installing Lago
###############

Lago is officially supported and tested on Fedora 24+ and CentOS 7.3+
distributions. However, it should be fairly easy to install it on any Linux
distribution that can run libvirt and qemu-kvm using `pip`_,
here we provide instructions also for Ubuntu 16.04 which we test from time to
time. Feel free to open PR if you got it running on a distribution which is not
listed here so it could be added.

pip
===

1. Install system package dependencies:

   A. CentOS 7.3+

   .. code:: bash

        $ yum install -y epel-release centos-release-qemu-ev
        $ yum install -y python-devel libvirt libvirt-devel \
            libguestfs-tools libguestfs-devel gcc libffi-devel \
            openssl-devel qemu-kvm-ev


   B. Fedora 24+

   .. code:: bash

       $ dnf install -y python2-devel libvirt libvirt-devel \
           libguestfs-tools libguestfs-devel gcc libffi-devel \
           openssl-devel qemu-kvm

   C. Ubuntu 16.04+

   .. code:: bash

      $ apt-get install -y python-dev build-essential libssl-dev \
          libffi-dev qemu-kvm libvirt-bin libvirt-dev pkg-config \
          libguestfs-tools libguestfs-dev


2. Install libguestfs Python bindings, as they are not available on PyPI [3]_:

   .. code:: bash

       $ pip install http://download.libguestfs.org/python/guestfs-1.36.4.tar.gz


3. Install Lago with pip:

   .. code:: bash

       $ pip install lago


4. Setup permissions(replacing USERNAME accordingly):

   * Fedora / CentOS:

     .. code:: bash

         $ sudo usermod -a -G qemu,libvirt USERNAME
         $ sudo usermod -a -G USERNAME qemu
         $ sudo chmod g+x $HOME


   * Ubuntu 16.04+ :

     .. code:: bash

         $ sudo usermod -a -G libvirtd,kvm USERNAME
         $ chmod 0644 /boot/vmlinuz*

5. Create a global share for Lago to store templates:

   .. code:: bash

       $ sudo mkdir -p /var/lib/lago
       $ sudo mkdir -p /var/lib/lago/{repos,store,subnets}
       $ sudo chown -R USERNAME:USERNAME /var/lib/lago


   *Note:* If you'd like to store the templates in a different location
   look at the Configuration_ section, and change ``lease_dir``,
   ``template_repos`` and ``template_store`` accordingly. This can be done
   after the installation is completed.


6. Restart libvirt:

   .. code:: bash

       $ systemctl restart libvirtd

7. Log out and login again

Thats it! Lago should be working now. You can jump to `Lago Examples`_.

RPM Based - Fedora 24+ / CentOS 7.3+
====================================

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



Manual RPM installation
-----------------------


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
  `Manual RPM Installation`_ section. After doing that, log out and log in again.
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
       Ubuntu `python-guestfs`.

.. _Configuration: Configuration.html
.. _`Lago Examples`: Lago_Examples.html
