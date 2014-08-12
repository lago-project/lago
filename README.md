# oVirt testing framework

A framework (library + utilities) to allow quick deployment of virtual machines
with predefined configurations.

## Introduction

This utility was created to facilitate system testing of oVirt, a system that 
has to be deployed on several machines. To avoid the need to clean-up and 
provision physical hosts, and to independent of network/storage unavailability,
it was decided to run all the machines on a single host, as VMs, with a virtual
network, and storage exported by those VMs.

The bare flow is the following:

* Create a prefix - directory where all the resoures of the running environment
will be placed.
* Start VMs - Create a virtual network and virtual machines according to a
provided specification.
* Run specific logic - Interact with VMs as if they were regular machines, over
IP.
* Create/revert snapshots
* Tear down the environment and all its resources.

### oVirt
Test scenarions for oVirt are written as unit-tests written in python using
python-nose and oVirt python SDK.

To prepare environment for testing, the following has to be done:

* Build VDSM/oVirt RPMs from source.
* Sync nightly oVirt repository
* Combine built RPMs and nightly sync into a repository local to the testing
environment.
* Bring up an HTTP server on the local virtual network of the environment and 
install RPMs on the virtual machines.


### building engine/VDSM
Most of the build process will happen in mock environment but 'dist' targets are going to be ran outside, so all the utilites used by for dist tar creation (autotools / pep8 / ???) have to be installed.

* [oVirt-Engine requirements](http://www.ovirt.org/OVirt_Engine_Development_Environment#RPM_based)
* [VDSM requirements](http://www.ovirt.org/Vdsm_Developers#Installing_the_required_packages)

## CLI
One of the ways to interact with the testing framework is the provided CLI. It contains several basic verbs:

* `init` - Create a directory the framework will utilize as root of exectuion. Stores all the resources required throughout its lifecycle.
* `start` - Start virtual appliances of the current deployment
* `stop` - Stop virtual appliances of the current deployment
* `snapshot` - Create snapshots of all the virtual machines in the environment.
* `revert` - Revert to previously created snapshot
* `shell` - Run scripts and execute shell commands on the virtual machines.
* `cleanup` - Cleans up the exection environment. Note: directory still needs to be deleted afterwards.

For specific parameters run with `--help`, to run locally without installing the libraries, use `testenv/testenvcli_local`.

### oVirt CLI
The above CLI also includes `ovirt` verb that has several *sub-verbs*:

* `reposetup` - Build RPMs, sync exteranal repositories and create a private combined repository for the environment.
* `deploy` - Install RPMs and configure the virtual machines.
* `runtest` - Run a series of `python-nose` compatible tests.
* `snapshot` - Stop all services and take a snapshot of the system.

Run with `--help` for more detailed help.

## Basic usage
For basic usage, examine function `testenv_run` in `contrib/jenkins/testenv_common.sh`. This function demonstrates the way oVirt jenkins uses the testing framework (throught the CLI) to perform tests.

## Setting up
Currently the code relies on various configurations, this list might be incomplete.

### Libvirt authentication
At the moment, library uses qemu:///system URL and authenticates with `testenv@ovirt` as username and `testenv` as password.

### Nested virtualization
Enable nested virtualization in the kernel on intel CPUs set kvm\_intel.nested parameter to 1, by either editing /etc/modprobe.d/modprobe.conf and adding this line: `options kvm_intel nested=1` or by adding `kvm_intel.nested=1` to kernel cmdline in grub


### sudo rules
qemu takes possession of the disks it uses, to be able to manipulate VM disks we need to the following rule:
```
jenkins    ALL = (qemu) NOPASSWD: /bin/qemu-img
```

### Subnet lease directory
To automatially allocate subnets, the library uses a global directory to manage leases. At the moment, this directory is `/var/lib/testenv/subnets/`. It must be writeable by current user in order for subnet allocation to succeed.

# Jenkins
Most of jenkins scripts are located in `contrib/jenkins/`. 

## sudo rules
Jenkins user runs without an attached shell, so the following sudo rules are advised for successful mock use:
```
Defaults:%jenkins !requiretty
Defaults:jenkins !requiretty
Defaults:%mock !requiretty
Defaults:mock !requiretty
```

## Virtual resources specification:
The spec is a JSON file with the following format: 


```json
{
    "net": {
        "name": "NET_NAME",
		"gw*": "IP.IP.IP.IP"
	},
	"domains": {
		"DOMAIN_NAME1" : {
		        "vcpu*": "VCPUS",
			"cpu*": "CPUS",
			"memory*": "MEM_SIZE",
			"disks": [
				{
					"name": "NAME",
					"dev": "vdX",
					"type": "(template|empty|file)",
					"format": "(qcow2|raw)",
					"template_name*": "PATH",
					"size": "SIZE",
					"path*": "PATH"
				}
			],
			"ip*": "IP.IP.IP.IP",
			"metadata*": {
				"key_1": "value_1",
				"key_2": "value_2"
			}
		}
}
```

* **net** - Specification of the network.
    * **net.name** - Name of the virtual network to create
    * **net.gw** - (Optional) Gateway for the newtork to be created, e.g. 192.168.2.1. If ommited one will be selected for the environment.
* **domains** - All the specifications of the VMs to be created.
    * **domains.NAME** - Specification of a specific VM named NAME:
        * **domains.NAME.vcpu** - (Optional) Number of VCPUs to allocate to the domain.
        * **domains.NAME.cpu** - (Optional) Number of CPUs visible to the domain.
        * **domains.NAME.memory** - (Optional) Memory size allocated to the domain, in megabytes.
        * **domains.NAME.disks** - Specs for all the disks for a specific VM.
            * **domains.NAME.disks[index].name** - Logical name of the disk, when bootstrapping a VM, various files are placed on the disk named 'root', otherwise name is ignored.
            * **domains.NAME.disks[index].dev** - Device ID that will be provided to libvirt, e.g. when provided 'vda', disk will be accessible as the first VirtIO Disk at /dev/vda
            * **domains.NAME.disks[index].type** - Type of the disk
                * *template* - Create the disk as on overlay of existing disk image with disk path provided in *template_name* used as the backing file
                * *empty* - Create an empty disk image, with size provided in *size* argument.
                * *file* - Use the path provided in *path* field as disk image (directly).
            * **domains.NAME.disks[index].type** - Format of the disk image to create, ignored for template disks (always created as qcow2).
            * **domains.NAME.disks[index].template_name** - (Optional) Path to used as backing file for template disk.
            * **domains.NAME.disks[index].size** - (Optional) Size of the new disk to create.
            * **domains.NAME.disks[index].path** - (Optional) Path to use when using *file* disk.
        * **domains.NAME.ip** - (Optional) IP that should be assigned to the VM inside the virtual network. If not provided one will be assigned to it.
        * **domains.NAME.metadata** - (Optional) Metadata dictionary specific to the domain.

An example config is available at contrib/ovirt/config/virt/centos6.json
### oVirt specific
oVirt uses metadata field to attach properties to hosts:


* **ovirt-role** - Marks the role of the vm, current possible values are 'engine' and 'host'
* **ovirt-capabilities** - List of capabilities of VMs, that can be checked upon staring a test.
