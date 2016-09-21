Installation
=============

In order to install the framework, you'll need to build RPMs or acquire them
from a repository.

Repository
~~~~~~~~~~

Latest lago RPMs are built by jenkins job and you can find them in the ci
jobs::

    http://jenkins.ovirt.org/search/?q=lago_master_build-artifacts

Choose one of the results in this list according to your preferred distribution.

Or you can use the yum repo (it's updated often right now, and a bit
unstable), you can add it as a repository creating a file under
`/etc/yum.repos.d/lago.repo` with the following content:

For Fedora::

    [lago]
    baseurl=http://resources.ovirt.org/repos/lago/stable/0.0/rpm/fc$releasever
    name=Lago
    enabled=1
    gpgcheck=0

For EL distros (such as CentOS, RHEL, etc.)::

    [lago]
    baseurl=http://resources.ovirt.org/repos/lago/stable/0.0/rpm/el$releasever
    name=Lago
    enabled=1
    gpgcheck=0


**Note** It is possible that during the setup you'll need some extra python packages
that can be acquired from `here <https://fedoraproject.org/wiki/EPEL/>`_.

**TODO**: point to the release rpm once it's implemented, and use gpgcheck=1

Once you have them, install the following packages::

    $ yum install python-lago

This will install the needed package.


libvirt
~~~~~~~~~

Make sure libvirt is configured to run::

    $ systemctl enable libvirtd
     $ systemctl start libvirtd

SELinux
~~~~~~~~
At the moment, this framework might encounter problems running while SELinux
policy is enforced.

To disable SELinux on the running system, run::

    $ setenforce 0

To disable SELinux from start-up, edit `/etc/selinux/config` and set::

    SELINUX=permissive

User setup
~~~~~~~~~~~~~

Running lago requires certain permissions, so the user running it should be
part of certain groups.

Add yourself to lago and qemu groups::

    $ usermod -a -G lago USERNAME
     $ usermod -a -G qemu USERNAME

- The first command will let Lago to cache images and store some necessary files in '/var/lib/lago/'
- The second command will let Lago the ability to connect to the local libvirt socket.

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

That's It ! You have finished the installation process, now it's time to create some
cool virtual environment :)

**NOTE**: In order to enable nested virtualization check this
`document <EnableNested>`_
