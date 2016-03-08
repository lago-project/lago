..
    # Copyright 2014 Red Hat, Inc.
    #
    # This program is free software; you can redistribute it and/or modify
    # it under the terms of the GNU General Public License as published by
    # the Free Software Foundation; either version 2 of the License, or
    # (at your option) any later version.
    #
    # This program is distributed in the hope that it will be useful,
    # but WITHOUT ANY WARRANTY; without even the implied warranty of
    # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    # GNU General Public License for more details.
    #
    # You should have received a copy of the GNU General Public License
    # along with this program; if not, write to the Free Software
    # Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
    #
    # Refer to the README and COPYING files for full details of the license
    #

CI Process
=================

Here is described the usual workflow of going through the CI process from
starting a new branch to getting it merged and released in the
`unstable repo`_.


Starting a branch
---------------------
First of all, when starting to work on a new feature or fix, you have to start
a new branch (in your fork if you don't have push rights to the main repo).
Make sure that your branch is up to date with the project's master::

    git checkout -b my_fancy_feature
    # in case that origin is already lago-project/lago
    git reset --hard origin/master

Then, once you can just start working, doing commits to that branch, and
pushing to the remote from time to time as a backup.

Once you are ready to run the ci tests, you can create a pull request to master
branch, if you have `hub`_ installed you can do so from command line, if not
use the ui::

    $ hub pull-request

That will automatically trigger a test run on ci, you'll see the status of the
run in the pull request page. At that point, you can keep working on your
branch, probably just rebasing on master regularly and maybe amending/squashing
commits so they are logically meaningful.


A clean commit history
------------------------

An example of not good pull request history:

   * Added right_now parameter to virt.VM.start function
   * Merged master into my_fancy_feature
   * Added tests for the new parameter case
   * Renamed right_now parameter to sudo_right_now
   * Merged master into my_fancy_feature
   * Adapted test to the rename

This history can be greatly improved if you squashed a few commits:

   * Added sudo_right_now parameter to virt.VM.start function
   * Added tests for the new parameter case
   * Merged master into my_fancy_feature
   * Merged master into my_fancy_feature

And even more if instead of merging master, you just rebased:

   * Added sudo_right_now parameter to virt.VM.start function
   * Added tests for the new parameter case

That looks like a meaningful history :)

Rerunning the tests
----------------------

While working on your branch, you might want to rerun the tests at some point,
to do so, you just have to add a new comment to the pull request with one of
the following as content:

* ci test please
* ci :+1:
* ci :thumbsup:

Asking for reviews
--------------------
If at any point, you see that you are not getting reviews, please add the label
'needs review' to flag that pull request as ready for review.


Getting the pull request merged
--------------------------------
Once the pull request has been reviewed and passes all the tests, an admin can
start the merge process by adding a comment with one of the following as
content:

* ci merge please
* ci :shipit:

That will trigger the merge pipeline, that will run the tests on the merge
commit and deploy the artifacts to the `unstable repo`_ on success.

.. _`unstable repo`: http://resources.ovirt.org/repos/lago/unstable/0.0
.. _`hub`: https://github.com/github/hub
