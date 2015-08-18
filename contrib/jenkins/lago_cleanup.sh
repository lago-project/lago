#!/bin/bash
source $WORKSPACE/lago/contrib/jenkins/lago_common.sh

cd $PREFIX
$LAGOCLI cleanup
