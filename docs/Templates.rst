##############
Lago Templates
##############
We maintain several templates which are publicly available here_, and Lago
will use them by default. We try to ensure each of those templates is fully
functional out of the box. All templates are more or less the same as the
standard cloud image for each distribution.

The templates specification and build scripts are managed in a different
repository_, and it should be fairly easy to create your own templates
repository.

Available templates
===================

+------------------+--------------+
| Template name    | OS           |
+------------------+--------------+
| el7-base         | CentOS 7.2   |
+------------------+--------------+
| el7.3-base       | CentOS 7.3   |
+------------------+--------------+
| fc23-base        | Fedora 23    |
+------------------+--------------+
| fc24-base        | Fedora 24    |
+------------------+--------------+
| fc25-base        | Fedora 25    |
+------------------+--------------+
| el6-base         | CentOS 6.7   |
+------------------+--------------+
| debian8-base     | Debian 8     |
+------------------+--------------+
| ubuntu16.04-base | Ubuntu 16.04 |
+------------------+--------------+

Repository metadata
===================

A templates repository should contain a `repo.metadata` file describing all
available templates. The repository build script creates this file 
automatically. The file contains a serialized JSON object with the following
members:

    ``name``: 
        The name of the repository.
    
    ``sources``: 
        
        ``<name>``: Name of a source.
        
            *TO-DO: no docs yet...*
    
    ``templates``: 
    
        ``<name>``: Unique template name.
        
            ``versions``:
                
                ``<version>``: Unique version string.
                
                    ``source``:
                        Name of the source from which this template version 
                        was created.
                        
                    ``timestamp``:
                        Creation time of the template version.
                        
                    ``handle``:
                        Either a base file name of the template located in the
                        root directory of the repository, or a root-relative
                        path to the template file.

.. _here: http://templates.ovirt.org/repo/
.. _repository: https://github.com/lago-project/lago-images
