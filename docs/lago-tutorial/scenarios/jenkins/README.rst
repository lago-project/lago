About
~~~~~~

This environment will consist of 3 vm's that will simulate
a Jenkins infrastructure.

"vm0-server" - Jenkins server
"vm1-slave" - Jenkins slave
"vm2-slave" - Jenkins slave


Adding The Slaves
~~~~~~~~~~~~~~~~~~

Open your browser and enter to the Jenkins web UI.
The address should be like: "put-your-server-ip-here:8080"
In the UI do the following:

-  Go to Manage Jenkins >> Manage nodes
-  Click on: New node
-  Enter a name for the new slave (you can pick whatever name you like)
   and mark "Dumb Slave", now hit OK
-  Enter "/jenkins" in "Remoote Root Directory" (This is were Jenkins
   will place his files in the slave)
-  Enter the slave's ip in "Host"
-  Near the "Credentials" label, click on "add"
-  Enter: Username = "root", Password = "123456" - this is the root password of the vms. for more information about configuring the root password with Lago, check out
   `Lago's website <http://lago.readthedocs.org/en/latest/README.html>`__
-  hit the "Save" button
-  Repeat the process for the other slave.

Your server is now configured with the new slaves.
