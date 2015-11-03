# System testing framework: getting started

Hello, this describes how to get started with oVirt testing framework.


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
$ yum install python-lago lago python-lago-ovirt lago-ovirt lago-ovirt-extras
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

        ```
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


```
$ usermod -a -G lago USERNAME
$ usermod -a -G mock USERNAME
$ usermod -a -G qemu USERNAME
```

It is also advised to add qemu user to your group (to be able to store VM files
in home directory):


```
$ usermod -a -G USERNAME qemu
```

For the group changes to take place, you'll need to re-login to the shell.
Make sure running `id` returns all the aforementioned groups.


## Preparing the workspace

Create a directory where you'll be working, *make sure qemu user can access it*.

We will be using the example configurations of lago, for a custom setup you
might want to create your own.


## Running the testing framework

Run the example script:

`/usr/share/ovirtlago/examples/el6engine_el7hosts_ovirt3.5.sh`

Remember that you don't need root access to run it, if you have permission
issues, make sure you followed the guidelines in the section *user setup*
above

This will take a while, as first time execution downloads a lot of stuff.

Once it is done, the framework will contain a 3.5 engine with all the
hosts and storage added, the environment itself will be deployed in
test-deployment directory.

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
$ cd lago-example-prefix
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

```
$ cd test-deployment
$ lagocli cleanup
```


## The example script in detail

This section explains step by step the contents of the example script at:
`/usr/share/ovirtlago/examples/el6engine_el7hosts_ovirt3.5.sh`

The following example creates an environment at `$PWD/lago-test-prefix`, with
the following virtual machines:

* `storage-iscsi`: Fedora 20 with an iSCSI target and 10 exposed LUNs
* `storage-nfs`: Fedora 20 with several NFS exports
* `engine`: CentOS 6 with 3.5 oVirt engine installed.
* `host[0-3]`: CentOS 7 with 3.5 VDSM deployed and connected to the engine.


### Preparation:

```shell
WORKSPACE=$PWD

# location where lago installed the ovirt extras files
OVIRT_CONTRIB="/usr/share/ovirtlago"

# file defining the environment layout (machines, nets, disks...)
VIRT_CONFIG="${OVIRT_CONTRIB}/config/virt/centos7.json"

# yum repo file containing all the needed extra repos (aside from base os)
REPOSYNC_YUM_CONFIG="${OVIRT_CONTRIB}/config/repos/ovirt-3.5.repo"

# file describing the vm images repository
STORE_CONFIG="${OVIRT_CONTRIB}/config/stores/ci.json"

# file with the responses for the ovirt engine setup process
ANSWER_FILE="${OVIRT_CONTRIB}/config/answer-files/el6_3.5.conf"

PREFIX="${WORKSPACE}/lago-example-prefix"
chmod g+x "${WORKSPACE}"
rm -rf "$PREFIX"
```

This will set the needed env vars, make sure the group has access (so qemu can
access the prefix) and remove any leftovers from any previous run.


### Step 1: Create the testing environment

```shell
lagocli init \
    "${PREFIX}" \
    "${VIRT_CONFIG}" \
    --template-repo-path="$STORE_CONFIG"
echo '[INIT_OK] Initialized successfully, will need cleanup later'
```

This step creates a new environment at `$PREFIX` using the `init`
verb of the lagocli, see `lagocli init --help` for more information on
the parameters.

After this step, no virtual resources are launched yet, but the environment
directory now contains all the information required to launch them later on.

First time this command is ran, it might take a while to complete, because
the templates have to be downloaded (only once) and prepared for the run.

```shell
cd "${PREFIX}"
```

All `lagocli` verbs interacting with an existing environment assume that
the environment was created at the current working directory.


### Step 2: Build RPM repository

```shell
lagocli ovirt reposetup \
    --reposync-yum-config="${REPOSYNC_YUM_CONFIG}"
```

The `reposetup` verb is responsible for construction of the internal repository.
The internal repository is served to the VMs during various steps.

The internal reposirtory is built from one or several 'sources', there are 2
types of sources:

* External RPM repositories:

    A yum .repo file can be passed to the verb, and all the included repositories
    will be downloaded using 'reposync' and added to the internal repo.

* RPMs build from sources:

    At the moment of writing, this utility knows to build 3 projects from source:

    * ovirt-engine
    * vdsm
    * vdsm-jsonrpc-java

    All the builds are launched inside mock so mock permissions are required if
    anything is to be built from source. That way host distro does not have to
    match the distro of the VMs.
    RPMs build from source take precedence over ones synced from external repos.


### Step 3: Bring up the virtual resources

```shell
lagocli start
```

This starts all resources (VMs, bridges), at any time, you can use the `stop`
verb to stop any active resources.


### Step 4: Run initial setup scripts

```shell
lagocli ovirt deploy
```


### Step 5: Configure the engine

```shell
lagocli ovirt engine-setup \
    --config="${ANSWER_FILE}"
```


### Step 6: Deploy hosts, and add storage domains (sanity tests)

```shell
lagocli ovirt runtest \
    "${OVIRT_CONTRIB}/test_scenarios/bootstrap_3_5.py" \
...
lagocli ovirt runtest \
    "${OVIRT_CONTRIB}/test_scenarios/create_clean_snapshot.py" \
&& lagocli ovirt runtest \
    "${OVIRT_CONTRIB}/test_scenarios/basic_sanity.py"
```

This test runs a simple test case on the environment:

* Create a new DC and cluster
* Deploy all the hosts
* Add storage domains
* Import templates

The tests are written in python and interact with the environment using the
python SDK.


### Step 6: Collect the logs


```shell
lagocli ovirt collect \
    --output "${PREFIX}/test_logs/post_bootstrap"
...
lagocli ovirt collect \
    --output "${PREFIX}/test_logs/post_basic_sanity"
```

The `ovirt collect` verb connects to the virtual machines and collects any
relevant logs from them and stores them into the directories specified. You can
see all the logs now there:

```shell
$ tree test_logs
test_logs/
└── bootstrap.add_cluster-20151029093323
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
