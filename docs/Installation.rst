Installing Lago
---------------

You'll notice that some of the actions you need to do to run Lago are
currently manual, but we are working to add them as part of the standard
Python packaging for Lago which is in progress.

Setting up yum repos
^^^^^^^^^^^^^^^^^^^^
Currently only RPM installation is available but we are working on adding support for Ubuntu and Debian soon.

Add the following repos to a lago.repo file in your /etc/yum.repos.d/ dir:

For Fedora::

  [lago]
  baseurl=http://resources.ovirt.org/repos/lago/stable/0.0/rpm/fc$releasever
  name=Lago
  enabled=1
  gpgcheck=0

For EL distros (such as CentOS, RHEL, etc.), make sure you have EPEL and::

  [lago]
  baseurl=http://resources.ovirt.org/repos/lago/stable/0.0/rpm/el$releasever
  name=Lago
  enabled=1
  gpgcheck=0


.. todo:: point to the release rpm once it's implemented, and use gpgcheck=1

Installing the packages
^^^^^^^^^^^^^^^^^^^^^^^

Once you have them, install the following packages::

   $ yum install python-lago lago

This will install all the needed packages to get you up and running with Lago.

Configuring Libvirt
^^^^^^^^^^^^^^^^^^^
Make sure libvirt is configured to run::

        $ systemctl enable libvirtd
        $ systemctl start libvirtd


User permissions setup
^^^^^^^^^^^^^^^^^^^^^^

Running lago requires certain permissions, so the user running it should be
part of certain groups.

Add yourself to lago and qemu groups::

    $ usermod -a -G lago USERNAME
    $ usermod -a -G qemu USERNAME

It is also advised to add qemu user to your group (to be able to store VM files
in home directory)::

    $ usermod -a -G USERNAME qemu

For the group changes to take place, you'll need to re-login to the shell.
Make sure running `id` returns all the aforementioned groups.

Make sure that the qemu user has execution rights to the dir where you will be
creating the prefixes, you can try it out with::

    $ sudo -u qemu ls /path/to/the/destination/dir

If it can't access it, make sure that all the dirs in the path have your user
or qemu groups and execution rights for the group, or execution rights for
other (highly recommended to use the group instead, if the dir did not have
execution rights for others already)

It's very common for the user home directory to not have group execution
rights, to make sure you can just run::

    $ chmod g+x $HOME

And, just to be sure, let's refresh libvirtd service to ensure that it
refreshes it's permissions and picks up any newly created users::

    $ sudo service libvirtd restart

Iptables must allow internal connection to the internal repository lago publishes:

    $ echo "-A INPUT -p tcp --dport 8585 -j ACCEPT" >> /etc/sysconfig/iptables
    $ service iptables reload
