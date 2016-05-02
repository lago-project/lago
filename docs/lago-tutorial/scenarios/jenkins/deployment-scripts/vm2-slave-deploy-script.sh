#!/bin/bash -xe
yum install -y java-1.8.0-openjdk-devel.x86_64 \
  net-tools.x86_64

# As this is the same as vm1, you can use the same script, or soft-link from
# one to the other
