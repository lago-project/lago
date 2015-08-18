export IMAGES_REPO=$WORKSPACE/lago-images-repo
export LAGO=$WORKSPACE/lago

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

cd $WORKSPACE/lago

export PYTHONPATH=$PWD/lib:%PYTHONPATH
export PATH=$PWD/libexec:$PATH

$LAGO/bin/update_images.py \
	$LAGO/update-deployment \
	$WORKSPACE/lago/scripts/update_if_needed.sh \
	$IMAGES

if [ $? -ne 0 ]
then
	echo 'Skipping commit'
	exit 0
fi

cd $IMAGES_REPO
git commit -avs -m "Updated $(date -I)" || true
git push origin/master
