#!/bin/bash -xe
mkdir -p "/var/log/vdsm"
echo "fancy log" >/var/log/vdsm/fancylog.log
echo "fancy log number 2" >/var/log/vdsm/fancylog2.log
sync
