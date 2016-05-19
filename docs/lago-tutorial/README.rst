Lago-Tutorial
=============

In this guide you will find an explanation about the different concepts
and features of Lago. By reading this document, you should gain the ability to setup
your own custom virtual environment.

If it's your first time with Lago, it is advised to check `this demo <https://github.com/gbenhaim/Lago-Demo>`__,
in order to get an overview about the flow.

Prerequisites
^^^^^^^^^^^^^

Install Lago - follow
`this <../README.html#installation>`__ tutorial
for more information

Creating the working directory
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

//TODO: add a defualt init file to lago

Configuring The environment  
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

//TODO: explain about the init file 

-  init.json – This is the file which describes the structure of our
   environment: the specification of the vms, networks, the path and
   name of the deployment scripts for each vm.


The init.json is where we need to describe our environment e.g vms and
networks, so Lago can create them for us.

//TODO: elaborate about the different features and values that can be
specified within the file.


Templates and storage
^^^^^^^^^^^

//TODO: explain about install from templae, usin qucow2 file, iso etc... 

The network
^^^^^^^^^^^

Lago allows for a creation of 10 different lans ranging from:
192.168.200.x to 192.168.209.x
The subnet will be automatically assigend to the virtual network
bridge.


Creating the environment
^^^^^^^^^^^^^^^^^^^^^^^^

We can use two different approches:

Manual Configurations:

::

    lago init lago-work-dir init.json

(This should be invoked from: /lago-tutorial/scenarios/jenkins)

-  The directory /lago-work-dir will contain the files of our new Lago
   environment.
   This directory shouldn't exist before invoking lago init.
   
-  --template-repo-path, for specifing the path to the template-repo
   file. (The templates repository is the place from which the base “qcow2” virtual disks will be copied from).
   By default Lago will use the file from: http://templates.ovirt.org/repo/repo.metadata\
   
-  init.json, the name of the file which describes our environment.

Auto configurations

::

    lago init

This command will use the following default configurations:

-  The command will search for a file named "LagoInitFile" that will be
   used as the init file.
-  The workdir will be named ".lago"
-  As mentioned above, The default repo will be used.

Note: Lago will copy the deployment scripts into the new environment and set up two environment variables.
For example, if you were at /home/myuser/lago dir, 

- $LAGO_PREFIX_PATH = /home/myuser/lago/.lago/current
- $LAGO_WORKDIR_PATH = /home/myuser/lago/.lago/

so when using a relative path to the deployment (in the init file), there is no worry that 
the path will be broken when trying to deploy the vms from a directory that doesn't satisfy the relative path.
In general, all the other commands of lago can use those variables.

Deploy the VMs
^^^^^^^^^^^^^^

When using the manual configurations all the commands should be invoked
from /lago-work-dir.

When using the default workdir you can invoke commands from it's parent,
or any 'sibiling', for example:

::

    lago init
    mkdir lolo
    cd lolo
    lago status

Now, lets start the vms:

::

    lago start

Or for a specific vm named "server":

::

    lago start server

The command below will run the deployment scripts (from within the
vms) that were specified in the init.json file.

so, if you used the "manual configurations", the command should be
invoked from /lago-work-dir.

::

    lago deploy


Getting the state of the environment
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

You can get the information about the state of the enviorment with:

::

    lago status

Or for a formated output as json or yaml:

::

    lago --out-format [json | yaml] status

You can write down to yourself the ip adresses of the server and
slaves, because we will need them when configuring the server.

Interacting with the VMs
^^^^^^^^^^^^^^^^^^^^^^^^

Lago allows you to connect to the vms via ssh.
for exmaple, if we have a vm named "server" we will use the following:

::

    lago shell server

If the deployment scripts run successfuly we don't have
to connect to the machines.

In case of a failure, you can access the vms via console.
This is useful when the vm failed to boot or when trubleshooting
network issues.

::

    lago console server


Stop the environment
^^^^^^^^^^^^^^^^^^^^

In order to stop the machines (brute shutdown) we will use:

::

    lago stop

Or for a specific vm named "server":

::

    lago stop server

Removing the enviornment
^^^^^^^^^^^^^^^^^^^^^^^^

The following command will remove all the files
that relates to the environment.

::

    lago destroy


More Configurations 
^^^^^^^^^^^^^^^^^^^^

Here are some more configurations for other environments:

.. toctree::
    :maxdepth: 2
    
    scenarios/jenkins/README
