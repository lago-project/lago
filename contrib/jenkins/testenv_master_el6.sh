#!/bin/bash
source $WORKSPACE/testenv/contrib/jenkins/testenv_common.sh

ENGINE_DIST=el6
VDSM_DIST=el6
REPOSYNC_YUM_CONFIG=$OVIRT_CONTRIB/config/repos/ovirt-master-snapshot-external.repo
REPOSYNC_DIR=$WORKSPACE/ovirt-repo
VIRT_CONFIG=$OVIRT_CONTRIB/config/virt/centos6.json
DEPLOY_SCRIPTS=$OVIRT_CONTRIB/config/deploy/centos6.scripts.json

testenv_run
