#!/bin/bash
source $WORKSPACE/lago/contrib/jenkins/lago_common.sh

cd $WORKSPACE
if [ -d $PREFIX ]
then
    rm -rf $WORKSPACE/exported-archives $WORKSPACE/exported-archives.tar.gz
    mkdir $WORKSPACE/exported-archives 
    
    if [ -d $PREFIX/test_logs/ ]
    then
        cp -rav $PREFIX/test_logs/ $WORKSPACE/exported-archives/extracted_logs
    fi
    if [ -d $PREFIX/logs/ ]
    then
        cp -rav $PREFIX/logs/ $WORKSPACE/exported-archives/lago_logs
    fi

    if [ -d $PREFIX/build ]; then
        find $PREFIX/build -name '*.rpm' -exec rm '{}' \;
        cp -rav $PREFIX/build $WORKSPACE/exported-archives/build_logs
    fi

    rm -rf $PREFIX

    tar cvzf $WORKSPACE/exported-archives.tar.gz exported-archives/
fi
