Configuration
=============
The recommend method to override the configuration file is by letting
lago auto-generate them::

        $ mkdir -p $HOME/.config/lago
        $ lago generate-config > $HOME/.config/lago/lago.conf

This will dump the current configuration to ``$HOME/.config/lago/lago.conf``,
and you may edit it to change any parameters. Take into account you should
probably comment out parameters you don't want to change when editing the file.
Also, all parameters in the configuration files can be overridden by passing
command line arguments or with environment variables, as described below.



lago.conf format
^^^^^^^^^^^^^^^^
Lago runs without a configuration file by default, for reference-purposes,
when lago is installed from the official packages(RPM or DEB),
a commented-out version of lago.conf(INI format) is installed at
``/etc/lago/lago.conf``.

In ``lago.conf`` global parameters are found under the ``[lago]`` section.
All other sections usually map to subcommands(i.e. ``lago init`` command
would be under ``[init]`` section).

*Example*::

        $ lago generate-config
        > [lago]
        > # log level to use
        > loglevel = info
        > logdepth = 3
        > ....
        > [init]
        > # location to store repos
        > template_repos = /var/lib/lago/repos
        > ...



lago.conf look-up
^^^^^^^^^^^^^^^^^
Lago attempts to look ``lago.conf`` in the following order:

1. ``/etc/lago/lago.conf``
2. According to `XDG standards`_ , which are by default:

   * ``/etc/xdg/lago/lago.conf``
   * ``/home/$USER/.config/lago/lago.conf``

3. Any environment variables.
4. CLI passed arguments.


If more than one file exists, all files are merged, with the last occurrence
of any parameter found used.

.. _`XDG standards`:  https://standards.freedesktop.org/basedir-spec/basedir-spec-latest.html




Overriding parameters with environment variables
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
To differentiate between the root section in the configuration file,
lago uses the following format to look for environment variables::


        'LAGO_GLOBAL_VAR' -> variable in [lago] section
        'LAGO__SUBCOMMAND__PARAM_1' -> variable in [subcommand] section



Example: changing the ``template_store`` which ``init`` subcommand uses to
store templates::


        # check current value:
        $ lago generate-config | grep -A4 "init"
        > [init]
        > # location to store repos
        > template_repos = /var/lib/lago/repos
        > # location to store temp
        > template_store = /var/lib/lago/store

        $ export LAGO__INIT__TEMPLATE_STORE=/var/tmp
        $ lago generate-config | grep -A4 "init"
        > [init]
        > # location to store repos
        > template_repos = /var/lib/lago/repos
        > # location to store temp
        > template_store = /var/tmp
