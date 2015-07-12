#!/bin/bash -ex
BUILDS=$PWD/automation-build/
EXPORTS=$PWD/exported-artifacts/

rm -rf "$BUILDS" "$EXPORTS"
mkdir -p "$BUILDS"
mkdir -p "$EXPORTS/rpms"

make clean
make srpm rpm OUTPUT_DIR="$BUILDS"

cp -av "$BUILDS/dist" "$EXPORTS/"
cp -av "$BUILDS/rpmbuild/SRPMS/" "$EXPORTS/rpm/"
cp -av "$BUILDS/rpmbuild/RPMS/" "$EXPORTS/rpm/"
