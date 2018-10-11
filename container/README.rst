Lago Container
===============

Build
------

make lago-container RPM_PATH=${RPM_PATH}

$RPM_PATH: A directory that contains Lago's RPMs.

Run
----

scripts/run-lago-container.sh $lago_data_dir $image_name

$lago-data-dir: A directory that will be used to cache VM images
$image_name: Lago container image
$container_name (optional): A name for the lago container


Execute commands
-----------------

scripts/lago.sh LAGO_CMD

For example:

./scripts/lago.sh status
