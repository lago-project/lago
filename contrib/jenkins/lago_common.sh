LAGODIR=$(realpath $WORKSPACE/lago)
LAGOCLI=$LAGODIR/lago/lagocli_local
PREFIX=$WORKSPACE/jenkins-deployment-$BUILD_NUMBER
OVIRT_CONTRIB=$LAGODIR/contrib/ovirt
TEMPLATES_CLONE_URL="ssh://templates@66.187.230.22/~templates/templates.git"

export PYTHONPATH=$WORKSPACE/lago/lib:$PYTHONPATH


lago_run () {
	set -e
	chmod g+x $WORKSPACE

	# Checkout the correct refs for vdsm and engine:
	if [ ! -z $VDSM_HEAD ]
	then
	    cd $WORKSPACE/vdsm
	    git fetch origin $VDSM_HEAD && git checkout FETCH_HEAD
	    VDSM_PATH=$WORKSPACE/vdsm
	fi

	if [ ! -z $ENGINE_HEAD ]
	then
	    cd $WORKSPACE/ovirt-engine
	    git fetch origin $ENGINE_HEAD && git checkout FETCH_HEAD
	    ENGINE_PATH=$WORKSPACE/ovirt-engine
	fi

	cd $LAGODIR

	# Clone templates
	if [ ! -d $WORKSPACE/templates ]
	then
	    $LAGODIR/bin/sync_templates.py --create $TEMPLATES_CLONE_URL $WORKSPACE/templates
	else
	    $LAGODIR/bin/sync_templates.py $WORKSPACE/templates
	fi

	# Create $PREFIX for current run
	$LAGOCLI init $PREFIX
	echo '[INIT_OK] Initialized successfully, need cleanup later'

	# Build RPMs
	cd $PREFIX
	$LAGOCLI ovirt reposetup \
	    --rpm-repo=$REPOSYNC_DIR \
	    --reposync-yum-config=$REPOSYNC_YUM_CONFIG \
	    --engine-dir=$ENGINE_PATH \
	    --engine-dist=$ENGINE_DIST \
	    --vdsm-dir=$VDSM_PATH \
	    --vdsm-dist=$VDSM_DIST

	# Start VMs
	$LAGOCLI start $VIRT_CONFIG \
	    --templates-dir=$WORKSPACE/templates

	# Install RPMs
	$LAGOCLI ovirt deploy $DEPLOY_SCRIPTS \
	    $OVIRT_CONTRIB/setup_scripts

	# Start testing
	$LAGOCLI ovirt runtest $OVIRT_CONTRIB/test_scenarios/bootstrap.py
	$LAGOCLI ovirt snapshot
	$LAGOCLI ovirt runtest $OVIRT_CONTRIB/test_scenarios/basic_sanity.py
}
