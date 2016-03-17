#!/bin/bash -xe
mkdir -p "/var/log/ovirt-engine"
echo "fancy log" >/var/log/ovirt-engine/fancylog.log
echo "fancy log number 2" >/var/log/ovirt-engine/fancylog2.log
sync
