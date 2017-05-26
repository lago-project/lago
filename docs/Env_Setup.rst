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
packages and do some changes to the os, so it's really recommended that you
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


Running Lago in virtualenv
---------------------------
This was tested on a fresh Fedora-24 Cloud image, but should work on Fedora 23
and most likely with little package-names resolving on CentOS >7.

Install dependencies::

  > sudo dnf install -y redhat-rpm-config libvirt libvirt-devel \
     libguestfs-devel libguestfs-tools qemu-img qemu-kvm \
     libvirt-daemon git gcc libffi-devel python-devel \
     openssl-devel bats python-magic python-libguestfs

Note that ``python-magic`` and ``python-libguestfs`` are currently not
available on PyPI, so we have to install them from RPMs.

Install virtualenv::

  > sudo pip install virtualenv

Add your user to ``qemu`` group and vice versa::

  > sudo usermod -a -G qemu "$USER"
  > sudo usermod -a -G "$USER" qemu

Add a polkitd policy to allow your user to connect to libvirtd::

  > echo "polkit.addRule(function(action, subject) {
    if (action.id == \"org.libvirt.unix.manage\" &&
       subject.user == \"$USER\") {
          return polkit.Result.YES;
          }
        }); " | sudo tee "/etc/polkit-1/rules.d/50-libvirt-$USER.rules"

Enable nested virtualization(assuming Intel here)::

 > echo "options kvm-intel nested=y" | sudo tee /etc/modprobe.d/kvm-intel.conf
 > sudo bash -c 'modprobe -r kvm_intel && modprobe kvm_intel'

Enable libvirtd::

 > sudo bash -c 'systemctl enable libvirtd && systemctl start libvirtd'
 > sudo bash -c 'systemctl enable virtlogd && systemctl start virtlogd'

Update home directory permissions::

 > chmod g+x "$HOME"

We are going to create the following directory structure::

 .
 ├── data
 │   ├── repo - lago repo directory
 │   ├── store - lago template store directory
 │   └── subnets - lago subnets lease files
 ├── lago - lago git repository
 └── venv-lago - venv installed modules

Create the directories::

 > mkdir -p "$HOME"/data/{repo,store,subnets}

Overriding the ``subnet_lease_dir`` is still not supported, so we will
have to create the directory under ``/var/lib/lago``::

  > sudo mkdir -p /var/lib/lago
  > sudo chown "$USER:$USER" /var/lib/lago

Create a local ``.lago.conf`` file pointing to our new directory structure::

 > cat > "$HOME/.lago.conf" << EOF
   [lago]
   template_store=/home/$USER/data/store
   template_repos=/home/$USER/data/repo
   subnet_lease_dir=/home/$USER/data/subnets
   EOF

Setup and activate a virtualenv, dragging the libraries already installed by
the RPMs::

  > virtualenv --system-site-packages ~/venv-lago && \
      source "$HOME"/venv-lago/bin/activate

Install Lago's Python dependencies in the newly created virtualenv::

  > pip install -I enum dulwich flake8 libvirt-python lockfile \
      lxml mock paramiko pytest pyyaml scp stevedore xmltodict \
      configparser yapf==0.7.1 nose

Clone Lago from GitHub::

  > git clone https://github.com/lago-project/lago.git "$HOME/lago"

Finally install Lago in development mode::

  > cd "$HOME/lago" && python setup.py develop

Before running Lago commands, log out of your shell and login again to ensure
your session is in the ``qemu`` group.
You should now be able to run all Lago commands with the virtualenv activated,
while modifying Lago's code.

To smoke-test the environment, create a simple ``LagoInitFile`` with a
single VM(note that this is yaml, indentation matters)::

  > cat > "$HOME/lago/LagoInitFile" << EOF
  domains:
    host1:
      vm-type: default
      memory: 4096
      nics:
        1. net: lago
      disks:
        1. template_name: fc24-base
           type: template
           name: root
           dev: vda
           format: qcow2


  nets:
    lago:
      type: nat
      dhcp:
        start: 100
        end: 254
      management: true
  EOF

And run under ``$HOME/lago``::

  > lago init

Expected output::

        @ Initialize and populate prefix:
          # Initialize prefix:
            + Create prefix dirs:
            + Create prefix dirs: Success (in 0:00:00)
            + Generate prefix uuid:
            + Generate prefix uuid: Success (in 0:00:00)
            + Create ssh keys:
            + Create ssh keys: Success (in 0:00:00)
            + Tag prefix as initialized:
            + Tag prefix as initialized: Success (in 0:00:00)
          # Initialize prefix: Success (in 0:00:00)
          # Create disks for VM host1:
            + Create disk root:
            + Create disk root: Success (in 0:00:00)
          # Create disks for VM host1: Success (in 0:00:00)
          # Copying any deploy scripts:
          # Copying any deploy scripts: Success (in 0:00:00)
          # [Thread-1] Bootstrapping host1:
          # [Thread-1] Bootstrapping host1: Success (in 0:01:00)
          # Save prefix:
            + Save nets:
            + Save nets: Success (in 0:00:00)
            + Save VMs:
            + Save VMs: Success (in 0:00:00)
            + Save env:
            + Save env: Success (in 0:00:00)
          # Save prefix: Success (in 0:00:00)
        @ Initialize and populate prefix: Success (in 0:01:01)


Enjoy!

Running the tests in virtualenv
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To run the unit tests using ``pytest``::

  > pytest lago/tests/unit

For functional tests using ``bats``::

  > bats lago/tests/functional/*.bats

Note that you can also run ``mock_runner.sh`` in the same directory
that you setup the virtualenv. That way, for small changes you may run the
unittests and functional tests, and before submitting a PR, run the full CI
tests(which also check for multi-platform compatibility) locally using ``mock``.
