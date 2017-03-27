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
rm -rf "$BUILDS" "$EXPORTS"/*{.rpm,.tar.gz}
mkdir -p "$BUILDS"
mkdir -p "$EXPORTS"

make clean
make lago.spec

echo "installing RPM build dependencies"
$BUILDDEP -y lago.spec

echo "creating RPM"
make rpm OUTPUT_DIR="$BUILDS"

find "$BUILDS" \
    \( -iname \*.rpm -or -iname \*.tar.gz \) \
    -exec mv {} "$EXPORTS/" \;
