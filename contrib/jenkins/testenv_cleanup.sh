#!/bin/bash
source $WORKSPACE/testenv/contrib/jenkins/testenv_common.sh

cd $PREFIX
$TESTENVCLI cleanup
