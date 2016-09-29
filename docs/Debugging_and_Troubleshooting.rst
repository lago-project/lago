Debugging Lago Environment
==========================

Now that you've run any of the examples, you probably eager to dive into

the Lago environment and checkout the created VMs and resources.

This document will give you a taste of how to do it, but if you're interested<br>
In a deeper view, please checkout the full Lago tutorial (TBD).

We'll use the oVirt example for explaining how to debug the environment created.

Debugging the Lago environment created by oVirt system tests
------------------------------------------------------------

As the above script has become a bit complicated, and it's not (yet) part of
Lago itself, this section will do the same as the script, but step by step with
Lago only command to give you a better idea of what you have to do in a usual
project.

So, let's get back to the root of the ovirt-system-tests repo, and cd into the
basic_suite_4.0 dir::

    cd ovirt-system-tests/basic_suite_4.0

Let's take a look to what is in there::

    $ tree
    .
    ├── control.sh
    ├── deploy-scripts
    │   ├── add_local_repo.sh
    │   ├── bz_1195882_libvirt_workaround.sh
    │   ├── setup_container_host.sh
    │   ├── setup_engine.sh
    │   ├── setup_host.sh
    │   ├── setup_storage_iscsi.sh
    │   └── setup_storage_nfs.sh
    ├── engine-answer-file.conf
    ├── init.json.in
    ├── reposync-config.repo
    ├── template-repo.json
    └── test-scenarios
        ├── 001_initialize_engine.py
        ├── 002_bootstrap.py
        ├── 003_create_clean_snapshot.py
        └── 004_basic_sanity.py

We can ignore the `control.sh` script, as it's used by the `run_suite.sh` and
we don't care about that in this readme.


init.json.in: The heart of lago, virt configurations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This init.json.in file, is where we will describe all the virtual elements of
our test environment, usually, vms and networks.

In this case, as the file is shared between suites, it's actually a template
and we will have to change the `@SUITE@` string inside it by the path to the
current suite::

    $ suite_path=$PWD
    $ sed -e "s/@SUITE@/$suite_path/g" init.json.in > init.json

Now we have a full `init.json` file :), but we have to talk about another file
before being able to create the prefix:

Note that lago supports json and yaml formats for that file.


template-repo.json: Sources for templates
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This file contains information about the available disk templates and
repositories to get them from, we can use it as it is, but if you are in Red
Hat office in Israel, you might want to use the Red Hat internal mirrors there,
for that use the `common/template-repos/office.json` file instead, see next for
the full command line.

**NOTE**: You can use any other template repo if you specify your own json file
there

**TODO**: document the repo store json file format


Initializing the prefix
~~~~~~~~~~~~~~~~~~~~~~~~~

Now we have seen all the files needed to initialize our test prefix (aka, the
directory that will contain our env). To do so we have to run this::

    $ lagocli init \
        --template-repo-path=template-repo.json \
        deployment-basic_suite_4.0 \
        init.json

Remember that if you are in the Red Hat office, you might want to use the repo
mirror that's hosted there, if so, run this command instead::

    $ lagocli init \
        --template-repo-path=common/template-repos/office.json \
        deployment-basic_suite_4.0 \
        init.json

This will create the `deployment-basic_suite_4.0` directory and populate it
with all the disks defined in the `init.json` file, and some other info
(network info, uuid... not relevant now).

This will take a while the first time, but the next time it will use locally
cached images and will take only a few seconds!


If you are using run_suite.sh
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To use an alternate repository template file when running `run_suite.sh`,
you'll have to edit it for now, search for the init command invocation and
modify it there, at the time of writing this, if you want to use the Red Hat
Israel office mirror, you have to change this::

    38 env_init () {
    39     $CLI init \
    40         $PREFIX \
    41         $SUITE/init.json \
    42         --template-repo-path $SUITE/template-repo.json
    43 }

by::

    env_init () {
        $CLI init \
            $PREFIX \
            $SUITE/init.json \
            --template-repo-path common/template-repos/office.json
    }

reposync-config.repo: yum repositories to make available to the vms
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

This file contains a valid yum repos definition, it's the list of all the yum
repos that will be enabled on the vms to pull from. If you want to use any
custom repos just add the yum repo entry of your choice there and it will be
make accessible to the vms.

The internal repository is built from one or several 'sources', there are 2
types of sources:

* External RPM repositories:

    A yum .repo file can be passed to the verb, and all the included
    repositories will be downloaded using 'reposync' and added to the internal
    repo.

This is used by the `ovirt reposetup` verb. To prefetch and generate the local
repo, we have to run it::

    $ lagocli ovirt reposetup --reposync-yum-config="reposync-config.repo"

This might take a while the first time too, as it has to fetch a few rpms from
a few repos, next time it will also use a cache to speed things up
considerably.

**NOTE**: From now on, all the `lagocli` command will be run inside the
prefix, so cd to it::

    $ cd deployment-basic_suite_4.0

Bring up the virtual resources
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

We are ready to start powering up vms!

::

    # make sure you are in the prefix
    $ pwd
    /path/to/ovirt-system-tests/deployment-basic_suite_4.0
    $ lagocli start

This starts all resources (VMs, bridges), at any time, you can use the `stop`
verb to stop all active resources.


Run oVirt initial setup scripts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Once all of our vms and network are up and running, we have to run any setup
scripts that will configure oVirt in the machines, as we already described in
the `init.json` what scripts should be executed, the only thing left is to
trigger it::

    $ lagocli ovirt deploy

This should be relatively fast, around a minute or two, for everything to get
installed and configured


Running the tests
~~~~~~~~~~~~~~~~~~

Okok, so now we have our environment ready for the tests!! \\o/

Lets get it on, remember that they should be executed in order::

    $ lagocli ovirt runtest 001_initialize_engine.py
    ...
    $ lagocli ovirt runtest 002_bootstrap.py
    ...
    $ lagocli ovirt runtest 003_create_clean_snapshot.py
    ...
    $ lagocli ovirt runtest 004_basic_sanity.py
    ...

This tests run a simple test suite on the environment:

* Create a new DC and cluster
* Deploy all the hosts
* Add storage domains
* Import templates

The tests are written in python and interact with the environment using the
python SDK.


Collect the logs
~~~~~~~~~~~~~~~~~


So now we want to collect all the logs from the vms, to troubleshoot and debug
if needed (or just to see if they show what we expect). To do so, you can
just::

    $ lagocli ovirt collect \
        --output "test_logs"

We can run that command anytime, you can run it in between the tests also,
specifying different output directories if you want to see the logs during the
process or compare later with the logs once the tests finish.

You can see all the logs now in the dir we specified::

    $ tree test_logs
    test_logs/
    ├── engine
    │   └── _var_log_ovirt-engine
    │       ├── boot.log
    │       ├── console.log
    │       ├── dump
    │       ├── engine.log
    │       ├── host-deploy
    │       ├── notifier
    │       ├── ovirt-image-uploader
    │       ├── ovirt-iso-uploader
    │       ├── server.log
    │       └── setup
    │           └── ovirt-engine-setup-20151029122052-7g9q2k.log
    ├── host0
    │   └── _var_log_vdsm
    │       ├── backup
    │       ├── connectivity.log
    │       ├── mom.log
    │       ├── supervdsm.log
    │       ├── upgrade.log
    │       └── vdsm.log
    ├── host1
    │   └── _var_log_vdsm
    │       ├── backup
    │       ├── connectivity.log
    │       ├── mom.log
    │       ├── supervdsm.log
    │       ├── upgrade.log
    │       └── vdsm.log
    ├── host2
    │   └── _var_log_vdsm
    │       ├── backup
    │       ├── connectivity.log
    │       ├── mom.log
    │       ├── supervdsm.log
    │       ├── upgrade.log
    │       └── vdsm.log
    ├── host3
    │   └── _var_log_vdsm
    │       ├── backup
    │       ├── connectivity.log
    │       ├── mom.log
    │       ├── supervdsm.log
    │       ├── upgrade.log
    │       └── vdsm.log
    ├── storage-iscsi
    └── storage-nfs

Cleaning up
~~~~~~~~~~~~

As before, once you have finished playing with the prefix, you will want to
clean it up (remember to play around!), to do so just::

    $ lagocli cleanup


FAQ
----
#. How do I know if the ``run_suite.sh`` is stuck or still running?

   Sometimes the script is downloading very big files which might
   Seem to someone as the script is stuck.
   One hacky way of making sure the script is still working is
   to check the size and content of the store dir::

    $ ls -la /var/lib/lago/store

   This will show any templates being downloaded and file size
   changes.

