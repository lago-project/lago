#!/bin/bash -ex

# Create prefix for current run
lagocli init 							\
	$PWD/test-deployment						\
	/usr/share/ovirtlago/config/virt/centos7.json		\
	--template-repo-path=$PWD/lago-template-repositories/repo.json

echo '[INIT_OK] Initialized successfully, need cleanup later'

# Build RPMs
cd $PWD/test-deployment

lagocli ovirt reposetup 						\
    --reposync-yum-config=/usr/share/ovirtlago/config/repos/ovirt-master-snapshot-external.repo

# Start VMs
lagocli start

# Install RPMs
lagocli ovirt deploy

# Configure engine
lagocli ovirt runtest /usr/share/ovirtlago/test_scenarios/initialize_engine_el7.py
# Start testing
lagocli ovirt runtest /usr/share/ovirtlago/test_scenarios/bootstrap.py
