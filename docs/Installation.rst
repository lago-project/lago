Installing Lago
---------------

Running Lago & the various supported deployments requires installation of Lago_ & repoman_ projects.

Currently only RPM installation is avaialbe but we are working on adding support for Ubuntu and Debian soona

So stay tuned!

Add the following repos to a lago.repo file in your /etc/yum.repos.d/ dir:

For Fedora::

  [lago]
  baseurl=http://resources.ovirt.org/repos/lago/stable/0.0/rpm/fc$releasever
  name=Lago
  enabled=1
  gpgcheck=0

  [ovirt-ci-tools]
  baseurl=http://resources.ovirt.org/repos/ci-tools/fc$releasever
  name=oVirt CI Tools
  enabled=1
  gpgcheck=0

For EL distros (such as CentOS, RHEL, etc.)::

  [lago]
  baseurl=http://resources.ovirt.org/repos/lago/stable/0.0/rpm/el$releasever
  name=Lago
  enabled=1
  gpgcheck=0

  [ovirt-ci-tools]
  baseurl=http://resources.ovirt.org/repos/ci-tools/el$releasever
  name=oVirt CI Tools
  enabled=1
  gpgcheck=0

**TODO**: point to the release rpm once it's implemented, and use gpgcheck=1

Once you have them, install the following packages::

   > yum install python-lago lago python-lago-ovirt lago-ovirt

This will install all the needed packages.

.. _Lago: http://lago.readthedocs.io
.. _repoman:  http://repoman.readthedocs.io
