#!/bin/bash -ex
# Copyright 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#
BUILDS=$PWD/automation-build
EXPORTS=$PWD/exported-artifacts

if hash dnf &>/dev/null; then
    YUM='dnf builddep'
else
    YUM='yum-builddep'
fi

rm -rf "$BUILDS" "$EXPORTS"/*{.rpm,.tar.gz}
mkdir -p "$BUILDS"
mkdir -p "$EXPORTS"

make clean
make lago.spec
$YUM -y lago.spec
make rpm OUTPUT_DIR="$BUILDS"

find "$BUILDS" \
    \( -iname \*.rpm -or -iname \*.tar.gz \) \
    -exec mv {} "$EXPORTS/" \;
