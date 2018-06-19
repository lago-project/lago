Develop Tools
====================
.. Starting developing
====================

Everyone is welcome to send patches to lago, but we know that not everybody
knows everything, so here's a reference list of technologies and methodologies
that lago uses for reference.


Python!
----------
Lago is written in python 2.7 (for now), so you should get yourself used to
basic-to-medium python constructs and technics like:

* Basic python:
  Built-in types, flow control, pythonisms (import this)

* Object oriented programming (OOP) in python:
  Magic methods, class inheritance


Some useful resources:

* Base docs: https://docs.python.org/2.7/
* Built-in types: https://docs.python.org/2.7/library/stdtypes.html
* About classes:
  https://docs.python.org/2.7/reference/datamodel.html#new-style-and-classic-classes
* The Zen of Python::

    > python -c "import this"

    The Zen of Python, by Tim Peters

    Beautiful is better than ugly.
    Explicit is better than implicit.
    Simple is better than complex.
    Complex is better than complicated.
    Flat is better than nested.
    Sparse is better than dense.
    Readability counts.
    Special cases aren't special enough to break the rules.
    Although practicality beats purity.
    Errors should never pass silently.
    Unless explicitly silenced.
    In the face of ambiguity, refuse the temptation to guess.
    There should be one-- and preferably only one --obvious way to do it.
    Although that way may not be obvious at first unless you're Dutch.
    Now is better than never.
    Although never is often better than *right* now.
    If the implementation is hard to explain, it's a bad idea.
    If the implementation is easy to explain, it may be a good idea.
    Namespaces are one honking great idea -- let's do more of those!


Bash
------
Even though there is not much bash code, the functional tests and some support
scripts use it, so better to get some basics on it. We will try to follow the
same standards for it than the `oVirt project has`_.


Libvirt + qemu/kvm
-----------------------
As we are using intesively libvirt and qemu/kvm, it's a good idea to get
yourself familiar with the main commands and services:

* libvirt: http://libvirt.org
* virsh client: http://libvirt.org/virshcmdref.html
* qemu (qemu-img is useful to deal with vm disk images):
  https://en.wikibooks.org/wiki/QEMU/Images

Also, there's a library and a set of tools from the libguestfs_ project that
we use to prepare templates and are very useful when debugging, make sure you
play at least with virt-builder, virt-customize, virt-sparsify and guestmount.


Git + Github
--------------
We use git as code version system, and we host it on Github right now, so if
you are not familiar with any of those tools, you should get started with them,
specially you should be able to:


* Clone a repo from github
* Fork a repo from github
* Create/delete/move to branches (git checkout)
* Move to different points in git history (git reset)
* Create/delete tags (git tag)
* See the history (git log)
* Create/amend commits (git commit)
* Retrieve changes from the upstream repository (git fetch)
* Apply your changes on top of the retrieved ones (git rebase)
* Apply your changes as a merge commit (git merge)
* Squash/reorder existing commits (git rebase --interactive)
* Send your changes to the upstream (git push)
* Create a pull request


You can always go to `the git docs`_ though there is a lot of good literature
on it too.


Unit tests with py.test
--------------------------
Lately we decided to use `py.test`_ for the unit tests, and all the current
unit tests were migrated to it. We encourage adding unit tests to any pull
requests you send.


Functional tests with bats
---------------------------
For the functional tests, we decided to use `bats framework`_. It's completely
written in bash, and if you are modifying or adding any functionality, you
should add/modify those tests accordingly. It has a couple of custom
constructs, so take a look to the `bats docs`_ while reading/writing tests.


Packaging
------------
Our preferred distribution vector is though packages. Right now we are only
building for rpm-based system, so right now you can just take a peek on
`how to build rpms`_. Keep in mind also that we try to move as much of the
packaging logic as posible to the `python packaging system`_ itself too, worth
getting used to it too.


Where to go next
-----------------
You can continue `setting up your environment`_ and try running the examples
in the readme_ to get used to lago. Once you get familiar with it, you can pick
any of the `existing issues`_ and send a pull request to fix it, so you get
used to the `ci process`_ we use to get stuff developed flawlessly and quickly,
welcome!



  .. _`oVirt project has`: http://ovirt-infra-docs.readthedocs.org/en/latest/General/Infra_Bash_style_guide.html
  .. _`py.test`: http://pytest.org
  .. _libguestfs: http://libguestfs.org/
  .. _`bats framework`: https://github.com/sstephenson/bats
  .. _`bats docs`: https://github.com/sstephenson/bats#writing-tests
  .. _`the git docs`: http://www.git-scm.com/docs
  .. _`how to build rpms`: http://www.rpm.org/max-rpm/index.html
  .. _`python packaging system`: https://packaging.python.org/en/latest/distributing/
  .. _`setting up your environment`: Env_Setup.html
  .. _`readme`: README.html
  .. _`existing issues`: https://github.com/lago-project/lago/issues
  .. _`ci process`: CI.html
