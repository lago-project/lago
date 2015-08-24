#!/bin/bash -e
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running unit/static checks                 ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
make check-local
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running build/installation tests           ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
automation/build-artifacts.sh
# to allow negated groups in globs
shopt -s extglob
# fail if a glob turns out empty
shopt -s failglob
echo "Installing..."
if hash dnf &>/dev/null; then
    dnf install -y exported-artifacts/!(*.src).rpm
else
    yum install -y exported-artifacts/!(*.src).rpm
fi
echo "Making sure it's installed"
testenvcli -h
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'

