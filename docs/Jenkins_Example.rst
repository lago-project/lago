The Jenkins server example
^^^^^^^^^^^^^^^^^^^^^^^^^^

In this example we will learn how to set up a basic environment with Lago.
The environment will consist of three virtual machines that will host Jenkins infrastructure.

The VMs
^^^^^^^

-  "vm0-server" - Jenkins server
-  "vm1-slave" - Jenkins slave
-  "vm2-slave" - Jenkins slave

The network
^^^^^^^^^^^^

The vms will be connected to the same network, There will be also connectivity between the vms host and the internet.

Prerequisite
^^^^^^^^^^^^^

- `Install Lago <http://lago.readthedocs.io/en/latest/README.html#installation>`_
- Clone this repository to your machine.

::

    git clone https://github.com/lago-project/lago-demo.git

Let's start !
^^^^^^^^^^^^^^

From within the cloned repository, run the following commands:

-  Create the environment.

::

    lago init

-  Start the vms.

::

    lago start

-   Installing the vms:
   -  Jenkins will be installed on the server.
   -  OpenJDK will be installed on the slaves.

::

    lago deploy

The environment is ready!
Now you can open your favorite browser, enter "vm0-server-ip-adress:8080" and the jenkins dashboard will be opened.
How to figure out what is the ip of "vm0-server" ?
Check out the following commands:

- Open a shell to vm0-server (for any other vm, just replace 'vm0-server' with the name of the machine)

::

    lago shell vm0-server

- Print some usefull information about the environment.

::

    lago status

When you done with the enviroment:

- Turn off the vms.

::

    lago stop



Note:
 To turn on the vms, use::

::

    lago start

And if you will not have a need for the environment in the future:

- Delete the vms.

::

    lago destroy


If this simple example just got you even more interested, join the major leauge and try out the
oVirt example! oVirt_Example_

.. _oVirt_Example: oVirt_Example.html 
