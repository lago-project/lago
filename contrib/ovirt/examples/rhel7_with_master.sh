#!/bin/bash -ex

# Create prefix for current run
testenvcli init 							\
	$PWD/test-deployment						\
	/usr/share/ovirttestenv/config/virt/centos7.json		\
	--template-repo-path=$PWD/testenv-template-repositories/repo.json

echo '[INIT_OK] Initialized successfully, need cleanup later'

# Build RPMs
cd $PWD/test-deployment

testenvcli ovirt reposetup 						\
    --reposync-yum-config=/usr/share/ovirttestenv/config/repos/ovirt-master-snapshot-external.repo

# Start VMs
testenvcli start

# Install RPMs
testenvcli ovirt deploy

# Configure engine
testenvcli ovirt runtest /usr/share/ovirttestenv/test_scenarios/initialize_engine_el7.py
# Start testing
testenvcli ovirt runtest /usr/share/ovirttestenv/test_scenarios/bootstrap.py
