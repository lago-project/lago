#!/bin/bash -ex
BUILDS=$PWD/automation-build
EXPORTS=$PWD/exported-artifacts

if hash dnf &>/dev/null; then
    YUM=dnf
else
    YUM=yum
fi

rm -rf "$BUILDS" "$EXPORTS"/*{.rpm,.tar.gz}
mkdir -p "$BUILDS"
mkdir -p "$EXPORTS"

make clean
make lago.spec
$YUM builddep -y lago.spec
make rpm OUTPUT_DIR="$BUILDS"

find "$BUILDS" \
    \( -iname \*.rpm -or -iname \*.tar.gz \) \
    -exec mv {} "$EXPORTS/" \;
