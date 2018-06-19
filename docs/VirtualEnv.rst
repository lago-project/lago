VirtualEnv setup
=================

How to set up your virtualenv for the lago project?


Requirements
-------------
Install virtual environment - virtualenv
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
virtualenv is a tool to create isolated Python environments.

Installation instructions:
https://virtualenv.pypa.io/en/stable/

Install virtualenvwrapper
~~~~~~~~~~~~~~~~~~~~~~~~~
virtualenvwrapper is a set of extensions to the virtualenv tool. 
The extensions include wrappers for creating and deleting virtual environments 
and otherwise managing your development workflow, making it easier to work on more 
than one project at a time without introducing conflicts in their dependencies.

Install instructions::
https://virtualenvwrapper.readthedocs.io/en/latest/


Configure Lago virtual environment:
---------------------------------------
  * Create a virtualenv for lago

    > mkvirtualenv lago_venv

  * Switch to the virtual env created:

    > workon lago_venv

  * Install Lago's requirements from pip(under lago repo):

    > pip install -r test-requires.txt

  * Install Lago in 'editable' mode.
    Whatever changes done the .py files will be reflected right away:

    > python setup.py develop

    Switching to branch, re-run 
    > python setup.py develop

    and you get the new branch installed. 

  * Install the 'lago-ost-plugin' in the virtualenv.
    To run OST - switch under the lago_venv to the plugin directory and run 
    > pip install -r test-requires.txt
    > python setup.py develop 
    
    so you get them both in editable mode.

#### ovirt-engine-sdk-python - add to reuiqremts.txt


