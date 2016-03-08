..
    # Copyright 2014 Red Hat, Inc.
    #
    # This program is free software; you can redistribute it and/or modify
    # it under the terms of the GNU General Public License as published by
    # the Free Software Foundation; either version 2 of the License, or
    # (at your option) any later version.
    #
    # This program is distributed in the hope that it will be useful,
    # but WITHOUT ANY WARRANTY; without even the implied warranty of
    # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    # GNU General Public License for more details.
    #
    # You should have received a copy of the GNU General Public License
    # along with this program; if not, write to the Free Software
    # Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
    #
    # Refer to the README and COPYING files for full details of the license
    #

Environment setup
=================

Here are some guidelines on how to set up your development of the lago project.


Requirements
-------------

You'll need some extra packages to get started with the code for lago, assuming
you are runnig Fedora::

  > sudo dnf install git mock libvirt-daemon qemu-kvm autotools

And you'll need also a few Python libs, which you can install from the repos or
use venv or similar, for the sake of this example we will use the repos ones::

  > sudo dnf install python-flake8 python-nose python-dulwich yapf

Yapf is not available on older Fedoras or CentOS, you can get it from the
`official yapf repo`_ or try on `copr`_.

Now you are ready to get the code::

  > git clone git@github.com:lago-project/lago.git

From now on all the commands will be based from the root of the cloned repo::

  > cd lago


Style formatting
------------------

We will accept only patches that pass pep8 and that are formatted with yapf.
More specifically, only patches that pass the local tests::

   > make check-local

It's recommended that you setup your editor to check automatically for pep8
issues. For the yapf formatting, if you don't want to forget about it, you can
install the pre-commit git hook that comes with the project code::

  > ln -s scripts/pre-commit.style .git/pre-commit

Now each time that you run `git commit` it will automatically reformat the code
you changed with yapf so you don't have any issues when submitting a patch.


Testing your changes
----------------------

Once you do some changes, you should make sure they pass the checks, there's no
need to run on each edition but before submitting a patch for review you should
do it.

You can run them on your local machine, but the tests themselves will install
packages and do some changes to the os, so it's really recommmended that you
use a vm, or as we do on the CI server, use mock chroots. If you don't want to
setup mock, skip the next section.

Hopefully in a close future we can use lago for that ;)


Setting up mock_runner.sh with mock (fedora)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For now we are using a script developed by the `oVirt` devels to generate
chroots and run tests inside them, it's not packaged yet, so we must get the
code itself::

  > cd ..
  > git clone git://gerrit.ovirt.org/jenkins

As an alternative, you can just download the script and install them in your
`$PATH`::

  > wget https://gerrit.ovirt.org/gitweb?p=jenkins.git;a=blob_plain;f=mock_configs/mock_runner.sh;hb=refs/heads/master

We will need some extra packages::

  > sudo dnf install mock

And, if not running as root (you shouldn't!) you have to add your user to the
newly created mock group, and make sure the current session is in that group::

  > sudo usermod -a -G mock $USER
  > newgrp mock
  > id  # check that mock is listed


Running the tests inside mock
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Now we have all the setup we needed, so we can go back to the lago repo and run
the tests, the first time you run them, it will take a while to download all the
required packages and install them in the chroot, but on consecutive runs it
will reuse all the cached chroots.

The `mock_runner.sh` script allows us to test also different distributions, any
that is supported by mock, for example, to run the tests for fedora 23 you can
run::

  > ../jenkins/mock_runner.sh -p fc23

That will run all the `check-patch.sh` (the `-p` option) tests inside a chroot,
with a minimal fedora 23 installation. It will leave any logs under the `logs`
directory and any generated artifacts under `exported-artifacts`.



   .. _`official yapf repo`: https://github.com/google/yapf
   .. _`copr`: https://copr.Fedoraproject.org/coprs/fulltext/?fulltext=yapf
