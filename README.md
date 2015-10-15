# System testing framework: getting started

Hello, this describes how to get started with oVirt testing framework.


## Installation

In order to install the framework, you'll need to build RPMs or acquire them
from a repository.

Latest lago RPMs are built by jenkin job and you can find them here:
http://jenkins.ovirt.org/job/lago_master_build-artifacts-[DIST]-x86_64

Where [DIST] is either el7, fc21 or fc22

Once you have them, install the following packages:
```
yum install lago-ovirt lago-ovirt-extras
```

This will install all the needed packages.

Note: on Fedora 20, you might need to enable `fedora-virt-preview` repository
to satisfy libvirt version requirement.

## Machine set-up

### Virtualization and nested virtualization support

1. Make sure that virtualization extension is enabled on the CPU, otherwise,
you might need to enable it in the BIOS. Generally, if virtualization extension
is disabled, `dmesg` log would contain a line similar to:

 ```
kvm: disabled by BIOS
```

1. To make sure that nested virtualization is enabled, run:

 ```
cat /sys/module/kvm_intel/parameters/nested
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

```
systemctl enable libvirtd
systemctl start libvirtd
```

### SELinux
At the moment, this framework might encounter problems running while SELinux
policy is enforced.

To disable SELinux on the running system, run ```setenforce 0```

To disable SELinux from start-up, edit ```/etc/selinux/config``` and set:

```
SELINUX=permissive
```


## User setup

Running a testing framework environment requires certain permissions, so the
user running it should be part of certain groups:

Add yourself to lago, mock and qemu groups:
```
usermod -a -G lago USERNAME
usermod -a -G mock USERNAME
usermod -a -G qemu USERNAME
```

It is also advised to add qemu user to your group (to be able to store VM files
in home directory):
```
usermod -a -G USERNAME qemu
```

For the group changes to take place, you'll need to re-login to the shell.
Make sure running `id` returns all the aforementioned groups.


## Preparing the workspace

Create a directory where you'll be working, make sure qemu user can access it.

Copy the json which contains the templates info:

```
https://raw.githubusercontent.com/oVirt/ovirt-testing-framework-tests/master/common/template-repos/office.json

OR

https://raw.githubusercontent.com/oVirt/ovirt-testing-framework-tests/master/common/template-repos/ci.json
```

The example script will search for those jsons under lago-template-repositories
directory, if you won't modify it you should have those json files over there
while running the example script below.

## Running the testing framework

This example script assumes templates on one of my hosts in my office, so
obviouly you'll have to be in the network when downloading them for the first
time.

Run the example script:
/usr/share/ovirtlago/examples/rhel7_with_master.sh

This will take a while, as first time execution downloads a lot of stuff.

Once it is done, the framework will contain the latest 3.5 engine with all the
hosts and storage added, the environment itsel will be deployed in
test-deployment directory.

To access it, log in to the web-ui at
* URL: `https://192.168.200.2/`
* Username: `admin@internal`
* Password: `123`

If you're running the framework on a remote machine, you can tunnel a local
port directly to the destination machine:
```
ssh -L 8443:192.168.200.2:443 remote-user@remote-ip
       ---- =================             ~~~~~~~~~
       (*)   (**)                         (***)

(*)   - The port on localhost that the tunnel will be available at.
(**)  - The destination where the remote machine will connect when local machine
        connects to the local end of the tunnel.
(***) - Remote machine through which we'll connect to the remote end of the
        tunnel.
```
After creating the tunnel, web-ui will be available at `https://localhost:8443/`


## Cleanup

Once you're done with the environment, run
```
cd test-deployment
lagocli cleanup
```


## The example script

The following example creates an environment at `$PWD/test-deployment`, with
the following virtual machines:
* `storage-iscsi`
  * Fedora 20 with an iSCSI target and 10 exposed LUNs
* `storage-nfs`
  * Fedora 20 with several NFS exports
* `engine`
  * RHEL7.1 with latest 3.5.x oVirt engine installed.
* `host[0-3]`
  * RHEL7.1 with latest 3.5.x VDSM deployed and connected to the engine.

### Step 1: Create the testing environment

```shell
lagocli init								\
    $PWD/test-deployment 						\
    /usr/share/ovirtlago/config/virt/centos7.json 			\
    --template-repo-path=$PWD/lago-template-repositories/repo.json
echo '[INIT_OK] Initialized successfully, need cleanup later'

```

* This step creates a new environment at `$PWD/test-deployment` using the `init`
verb of the lagocli, see `lagocli init --help` for more information on
the parameters.

* After this step, no virtual resources are launched yet, but the environment
directory now contains all the information required to launch them later on.

* First time this command is ran, it might take a while to complete, because
the templates have to be downloaded (only once).

```shell
cd $PWD/test-deployment
```

* All `lagocli` verbs interacting with an existing environment assume that
the environment was created at the current working directory.

### Step 2: Build RPM repository

```shell
lagocli ovirt reposetup \
    --reposync-yum-config=/usr/share/ovirtlago/config/repos/ovirt-master-snapshot-external.repo
```

The `reposetup` verb is responsible for construction of the internal repository.
The internal repository is served to the VMs during various steps.

The internal reposirtory is built from one or several 'sources', there are 2
types of sources:
* External RPM repositories:

  A yum .repo file can be passed to the verb, and all the included repositories
  will be downloaded using 'reposync' and added to the internal repo.

* RPMs build from source

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
lagocli ovirt runtest \
	/usr/share/ovirtlago/test_scenarios/initialize_engine_el7.py
```

### Step 6: Deploy hosts, and add storage domains

```shell
lagocli ovirt runtest /usr/share/ovirtlago/test_scenarios/bootstrap.py
```

This test runs a simple test case on the environment:

* Create a new DC and cluster
* Deploy all the hosts
* Add storage domains
* Import templates

The tests are written in python and interact with the environment using the
python SDK.
