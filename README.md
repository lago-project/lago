# Getting started

Hello, this describes how to get started with Lago.


## Installation

In order to install the framework, you'll need to build RPMs or acquire them
from a repository.

Latest lago RPMs are built by jenkin job and you can find them here:
http://jenkins.ovirt.org/job/lago_master_build-artifacts-$DIST-x86_64

Where `$DIST` is either el7, fc21 or fc22


Or you can use the yum repo (it's updated often right now, and a buit unstable):

http://resources.ovirt.org/repos/lago/rpm/$DIST

Where `$DIST` is either el7, fc21 or fc22

Once you have them, install the following packages:

```shell
$ yum install python-lago lago python-lago-ovirt lago-ovirt
```

This will install all the needed packages.

**TODO**:explain each package contents and goals

## Machine set-up

### Virtualization and nested virtualization support

1. Make sure that virtualization extension is enabled on the CPU, otherwise,
you might need to enable it in the BIOS. Generally, if virtualization extension
is disabled, `dmesg` log would contain a line similar to:

    ```shell
    kvm: disabled by BIOS
    ```

1. To make sure that nested virtualization is enabled, run:

    ```shell
    $ cat /sys/module/kvm_intel/parameters/nested
    ```

    This command should print `Y` if nested virtualization is enabled, otherwise,
    enable it the following way:

    1. Edit `/etc/modprobe.d/kvm-intel.conf` and add the following line:

        ```shell
        options kvm-intel nested=y
        ```
    1.  Reboot, and make sure nested virtualization is enabled.


### libvirt

Make sure libvirt is configured to run:

```shell
$ systemctl enable libvirtd
$ systemctl start libvirtd
```

### SELinux
At the moment, this framework might encounter problems running while SELinux
policy is enforced.

To disable SELinux on the running system, run:

```shell
$ setenforce 0
```

To disable SELinux from start-up, edit `/etc/selinux/config` and set:

```shell
SELINUX=permissive
```


## User setup

Running a testing framework environment requires certain permissions, so the
user running it should be part of certain groups:

Add yourself to lago, mock and qemu groups:


```shell
$ usermod -a -G lago USERNAME
$ usermod -a -G mock USERNAME
$ usermod -a -G qemu USERNAME
```

It is also advised to add qemu user to your group (to be able to store VM files
in home directory):


```shell
$ usermod -a -G USERNAME qemu
```

For the group changes to take place, you'll need to re-login to the shell.
Make sure running `id` returns all the aforementioned groups.


## Preparing the workspace

Create a directory where you'll be working, *make sure qemu user can access it*.

We will be using the example configurations of lago, for a custom setup you
might want to create your own.


## Running the testing framework

As an example, we will use the basic suite of the ovirt tests, so we have to
download them, you can run the following to get a copy of the repository:

```shell
$ git clone git://gerrit.ovirt.org/ovirt-system-tests
```

Once you have the code, you can run the run_suite.sh script to run any of the
suites available (right now, only 3.5 and 3.6 basic_suites are fully working):

```shell
$ cd ovirt-system-tests
$ ./run_suite.sh basic_suite_3.5
```

Remember that you don't need root access to run it, if you have permission
issues, make sure you followed the guidelines in the section *user setup*
above

This will take a while, as first time execution downloads a lot of stuff.

Once it is done, you will get the results in the directory
`deployment-basic_suite_3.5`, that will include an initialized prefix with a
3.5 engine vm with all the hosts and storages added.

To access it, log in to the web-ui at

* URL: `https://192.168.200.2/`
* Username: `admin@internal`
* Password: `123`

If you're running the framework on a remote machine, you can tunnel a local
port directly to the destination machine:

```shell
$ ssh -L 8443:192.168.200.2:443 remote-user@remote-ip
         ---- =================             ~~~~~~~~~
         (*)   (**)                         (***)

(*)   - The port on localhost that the tunnel will be available at.
(**)  - The destination where the remote machine will connect when local machine
        connects to the local end of the tunnel.
(***) - Remote machine through which we'll connect to the remote end of the
        tunnel.
```

After creating the tunnel, web-ui will be available at `https://localhost:8443/`


## Poke around in the env

You can now open a shell to any of the vms, start/stop them all, etc.

```shell
$ cd deployment-basic_suite_3.5
$ lagocli shell engine
[root@engine ~]# exit

$ lagocli stop
2015-11-03 12:11:52,746 - root - INFO - Destroying VM engine
2015-11-03 12:11:52,957 - root - INFO - Destroying VM storage-iscsi
2015-11-03 12:11:53,167 - root - INFO - Destroying VM storage-nfs
2015-11-03 12:11:53,376 - root - INFO - Destroying VM host3
2015-11-03 12:11:53,585 - root - INFO - Destroying VM host2
2015-11-03 12:11:53,793 - root - INFO - Destroying VM host1
2015-11-03 12:11:54,002 - root - INFO - Destroying VM host0
2015-11-03 12:11:54,210 - root - INFO - Destroying network lago

$ lagocli start
2015-11-03 12:11:46,377 - root - INFO - Creating network lago
2015-11-03 12:11:46,712 - root - INFO - Starting VM engine
2015-11-03 12:11:47,261 - root - INFO - Starting VM storage-iscsi
2015-11-03 12:11:47,726 - root - INFO - Starting VM storage-nfs
2015-11-03 12:11:48,115 - root - INFO - Starting VM host3
2015-11-03 12:11:48,573 - root - INFO - Starting VM host2
2015-11-03 12:11:48,937 - root - INFO - Starting VM host1
2015-11-03 12:11:49,296 - root - INFO - Starting VM host0
```


## Cleanup

Once you're done with the environment, run

```shell
$ cd deployment-basic_suite_3.5
$ lagocli cleanup
```

That will stop any running vms and remove the lago metadata in the prefix, it
will not remove any other files (like disk images) or anything though, so you
can play with them for further investigation if needed, but once executed, it's
safe to fully remove the prefix dir if you want to.


## Step by step now

As the above script has become a bit complicated, and it's not (yet) part of
lago itself, this section will do the same as the script, but step by step with
lago only command to give you a better idea of what you have to do in a ususal
project.

So, let's get back to the root of the ovirt-system-tests repo, and cd into the
basic_suite_3.5 dir:

```shell
cd ovirt-system-tests/basic_suite_3.5
```

Let's take a look to what is in there:

```shell
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
```

We can ignore the `control.sh` script, as it's used by the `run_suite.sh` and
we don't care about that in this readme.


### init.json.in: The heart of lago, virt configurations

This init.json.in file, is where we will describe all the virtual elements of
our test environment, usually, vms and networks.

In this case, as the file is shared between suites, it's actually a template
and we will have to change the `@SUITE@` string inside it by the path to the
current suite:

```shell
$ suite_path=$PWD
$ sed -e "s/@SUITE@/$suite_path/g" init.json.in > init.json
```

Now we have a full `init.json` file :), but we have to talk about another file
before being able to create the prefix:


### template-repo.json: Sources for templates

This file contains information about the available disk templates and
repositiories to get them from, we can use it as it is, but if you are in Red
Hat office, you might want to use the `../common/template-repos/office.json`
file instead.


### Initializing the prefix

Now we have seen all the files needed to initialize our test prefix (aka, the
directory that will contain our env). To do so we have to run this:

```shell
$ lagocli init \
     --template-repo-file=template-repo.json \
     deployment-basic_suite_3.5 \
     init.json
```

This will create the `deployment-basic_suite_3.5` directory and populate it
with all the disks defined in the `init.json` file, and some other info
(network info, uuid... not relevant now).

This will take a while the first time, but the next time it will use locally
cached images and will take only a few seconds!



### reposync-config.repo: yum repositories to make available to the vms

This file contains a valid yum repos definition, it's the list of all the yum
repos that will be enabled on the vms to pull from. If you want to use any
custom repos just add the yum repo entry of your choice there and it will be
make accessible to the vms.

The internal reposirtory is built from one or several 'sources', there are 2
types of sources:

* External RPM repositories:

    A yum .repo file can be passed to the verb, and all the included
    repositories will be downloaded using 'reposync' and added to the internal
    repo.

* RPMs build from sources:

    At the moment of writing, this utility knows to build 3 projects from
    source:

    * ovirt-engine
    * vdsm
    * vdsm-jsonrpc-java

    All the builds are launched inside mock so mock permissions are required
    if anything is to be built from source. That way host distro does not have
    to match the distro of the VMs. RPMs build from source take precedence
    over ones synced from external repos.


This is used by the `ovirt reposetup` verb. To prefetch and generate the local
repo, we have to run it:

```shell
$ lagocli ovirt reposetup --reposync-yum-config="reposync-config.repo"
```

This might take a while the first time too, as it has to fetch a few rpms from
a few repos, next time it will also use a chache to speed things up
considerably.

**NOTE**: From now on, all the `lagocli` command will be run inside the
prefix, so cd to it:

```shell
$ cd deployment-basic_suite_3.5
```

### Bring up the virtual resources

We are ready to start powering up vms!

```shell
# make sure you are in the prefix
$ pwd
    /path/to/ovirt-system-tests/deployment-basic_suite_3.5

$ lagocli start
```

This starts all resources (VMs, bridges), at any time, you can use the `stop`
verb to stop all active resources.


### Run oVirt initial setup scripts

Once all of our vms and network are up and running, we have to run any setup
scripts that will configure oVirt in the machines, as we already described in
the `init.json` what scripts should be executed, the only thing left is to
trigger it:

```shell
$ lagocli ovirt deploy
```

This should be relatively fast, around a minute or two, for everything to get
installed and configured


### Running the tests

Okok, so now we have our evironment ready for the tests!! \o/

Lets get it on, remember that they should be executed in order:

```shell
$ lagocli ovirt runtest 001_initialize_engine.py
...
$ lagocli ovirt runtest 002_bootstrap.py
...
$ lagocli ovirt runtest 003_create_clean_snapshot.py
...
$ lagocli ovirt runtest 004_basic_sanity.py
...
```

This tests run a simple test suite on the environment:

* Create a new DC and cluster
* Deploy all the hosts
* Add storage domains
* Import templates

The tests are written in python and interact with the environment using the
python SDK.


### Collect the logs


So now we want to collect all the logs from the vms, to troubleshoot and debug
if needed (or just to see if they show what we expect). To do so, you can just:

```shell
$ lagocli ovirt collect \
    --output "test_logs"
```

We can run that command anytime, you can run it in between the tests also,
specifying different output directories if you want to see the logs during the
process or compare later with the logs once the tests finish.

You can see all the logs now in the dir we specified:

```shell
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
```

### Cleaning up

As before, once you have finished playing with the prefix, you will want to
clean it up (remember to play around!), to do so just:

```shell
$ lagocli cleanup
```
