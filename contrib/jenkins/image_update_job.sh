export IMAGES_REPO=$WORKSPACE/testenv-images-repo
export TESTENV=$WORKSPACE/testenv

cd $IMAGES_REPO
git reset --hard
git fetch origin
git checkout master
git rebase origin/master

IMAGES=$(find $IMAGES_REPO/centos6 $IMAGES_REPO/centos7 -name '*.img')
echo 'Updating images:'
for IMAGE in $IMAGES; do
	echo $IMAGE
done

chmod 0666 $IMAGES

cd $WORKSPACE/testenv

export PYTHONPATH=$PWD/lib:%PYTHONPATH
export PATH=$PWD/libexec:$PATH

$TESTENV/bin/update_images.py \
	$TESTENV/update-deployment \
	$WORKSPACE/testenv/scripts/update_if_needed.sh \
	$IMAGES

if [ $? -ne 0 ]
then
	echo 'Skipping commit'
	exit 0
fi

cd $IMAGES_REPO
git commit -avs -m "Updated $(date -I)" || true
git push origin/master
