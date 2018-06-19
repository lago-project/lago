GIT Flow
=================

Fork & clone Repository
------------------------

Create a fork of lago project https://github.com/lago-project/lago to you github account.

    > git clone git@github.com:YOUR_GITHUB_USERNAME/lago.git

Configuring Remotes:

The origin remote will point to your fork

    > git remote -v
    
    origin	git@github.com:YOUR_GITHUB_USERNAME/lago.git (fetch)
    origin	git@github.com:YOUR_GITHUB_USERNAME/lago.git (push)

However, you also need to add a remote which points to the upstream repository:

    > git remote add upstream https://github.com/lago-project/lago.git

Which should leave you with the following remotes:

    > git remote -v
    
    origin  git@github.com:YOUR_GITHUB_USERNAME/lago.git (fetch)
    origin  git@github.com:YOUR_GITHUB_USERNAME/lago.git (push)
    upstream        https://github.com/lago-project/lago.git (fetch)
    upstream        https://github.com/lago-project/lago.git (push)
    
    Checking the status of your branch should show you’re up-to-date with your fork at the origin remote:

    > git status

    On branch YOUR_BRANCH
    Your branch is up-to-date with 'origin/YOUR_BRANCH'.
    nothing to commit, working tree clean

Create a branch
----------------
When starting to work on a new feature or fix, you have to start
a new branch (in your fork).
Make sure that your branch is up to date with the project's master::

    > git checkout -b my_fancy_feature

    # in case that origin is not synchronized 
    
    > git fetch upstream

    > git checkout master

    > git rebase upstream master

    > git checkout -b my_banch

    > git checkout master
    
    > git reset --hard upstream/master

    > git push -f

    > git checkout -b my_fancy_feature



The flow using rebase
---------------------------

Create a feature branch

    > git checkout -b feature

Make changes on the feature branch

    > echo "Test Text!" >>foo.py

    > git add foo.py

    > git commit -m 'Added comment'

Fetch upstream repository

    > git fetch upstream

Before you merge a feature branch back into your main branch (often master), 
your feature branch should be squashed down to a single buildable commit, 
and then rebased from the up-to-date main branch. Here’s a breakdown.    
    > git rebase -i HEAD~[NUMBER OF COMMITS]

    OR

    > git rebase -i [SHA]

Rebase changes from feature branch onto upstream/master

    > git rebase upstream/master

Rebase local master onto feature branch

    > git checkout master
    
    > git rebase feature

Push local master to upstream

    > git push upstream master


cherry-pick
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Cherry picking commits can be an effective way of getting code into your master branch. 
git cherry-pick is a special case of rebasing which takes a single commit and applies 
the changes on top of the current HEAD. 

    > git cherry-pick <commit id>





