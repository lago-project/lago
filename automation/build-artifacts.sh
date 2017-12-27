#!/bin/bash -ex
BUILDS=$PWD/automation-build
EXPORTS=$PWD/exported-artifacts

if hash dnf &>/dev/null; then
    YUM="dnf"
    BUILDDEP="dnf builddep"
else
    YUM="yum"
    BUILDDEP="yum-builddep"
fi
echo "cleaning $YUM metadata"
$YUM clean metadata

echo "cleaning $BUILDS, $EXPORTS"
rm -rf "$BUILDS" "$EXPORTS"/*{.rpm,.tar.gz} "$DIST"
mkdir -p "$BUILDS"
mkdir -p "$EXPORTS"

make clean
make python-sdist DIST_DIR="$PWD/exported-artifacts"
make clean
make lago.spec

echo "installing RPM build dependencies"
$BUILDDEP -y lago.spec

echo "creating RPM"
make rpm OUTPUT_DIR="$BUILDS"

find "$BUILDS" -iname "*.rpm" -exec mv {} "$EXPORTS/" \;
