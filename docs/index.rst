Welcome to the Lago project documentation!
==========================================

Lago Introduction
-----------------
Lago is an add-hoc virtual framework which helps you build virtualized
environments on your server or laptop for various use cases.

It currently utilizes 'libvirt' for creating VMs, but we are working on adding
more providers such as 'containers'.

.. todo:: Add the 'Lago story' and introduction.

Getting started
---------------

.. toctree::
    :maxdepth: 4

    Installation
    LagoInitFile
    SDK
    Lago_Examples
    Templates
    Configuration
    BUILD
    CPU

.. toctree::
    :caption: Developing
    :maxdepth: 2

    Env_Setup
    VirtualEnv
    CI
    Dev_Bootstrap


.. toctree::
   :caption: Contents
   :maxdepth: 4

   lago
   ovirtlago

.. toctree::
    :caption: Releases
    :maxdepth: 2

    Releases


Changelog
------------
Here you can find the `full changelog for this version`_

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`


.. _full changelog for this version: _static/ChangeLog.txt
