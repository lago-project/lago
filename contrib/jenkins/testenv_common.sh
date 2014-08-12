TESTENVDIR=$(realpath $WORKSPACE/testenv)
TESTENVCLI=$TESTENVDIR/testenv/testenvcli_local
PREFIX=$WORKSPACE/jenkins-deployment-$BUILD_NUMBER
OVIRT_CONTRIB=$TESTENVDIR/contrib/ovirt
TEMPLATES_CLONE_URL="ssh://templates@66.187.230.22/~templates/templates.git"

export PYTHONPATH=$WORKSPACE/testenv/lib:$PYTHONPATH


testenv_run () {
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

	cd $TESTENVDIR

	# Clone templates
	if [ ! -d $WORKSPACE/templates ]
	then
	    $TESTENVDIR/bin/sync_templates.py --create $TEMPLATES_CLONE_URL $WORKSPACE/templates
	else
	    $TESTENVDIR/bin/sync_templates.py $WORKSPACE/templates
	fi

	# Create $PREFIX for current run
	$TESTENVCLI init $PREFIX
	echo '[INIT_OK] Initialized successfully, need cleanup later'

	# Build RPMs
	cd $PREFIX
	$TESTENVCLI ovirt reposetup \
	    --rpm-repo=$REPOSYNC_DIR \
	    --reposync-yum-config=$REPOSYNC_YUM_CONFIG \
	    --engine-dir=$ENGINE_PATH \
	    --engine-dist=$ENGINE_DIST \
	    --vdsm-dir=$VDSM_PATH \
	    --vdsm-dist=$VDSM_DIST

	# Start VMs
	$TESTENVCLI start $VIRT_CONFIG \
	    --templates-dir=$WORKSPACE/templates

	# Install RPMs
	$TESTENVCLI ovirt deploy $DEPLOY_SCRIPTS \
	    $OVIRT_CONTRIB/setup_scripts

	# Start testing
	$TESTENVCLI ovirt runtest $OVIRT_CONTRIB/test_scenarios/bootstrap.py
	$TESTENVCLI ovirt snapshot
	$TESTENVCLI ovirt runtest $OVIRT_CONTRIB/test_scenarios/basic_sanity.py
}
