#!/usr/bin/env bats
#
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
load common
load helpers
load env_setup


FIXTURES="$FIXTURES/status"
PREFIX="$FIXTURES/prefix"


@test "status: setup" {
    rm -rf "$PREFIX"
    cp -a "$FIXTURES"/prefix_skel "$PREFIX"
    env_setup.populate_disks "$PREFIX"
}


@test "status: simple status run on stopped prefix" {
    pushd "$PREFIX" >/dev/null
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$PREFIX/expected"
}


@test "status: json status run on stopped prefix" {
    pushd "$PREFIX" >/dev/null
    helpers.run_ok "$LAGOCLI" --out-format json status
    helpers.diff_output "$PREFIX/expected.json"
}

@test "status: yaml status run on stopped prefix" {
    pushd "$PREFIX" >/dev/null
    helpers.run_ok "$LAGOCLI" -f yaml status
    helpers.diff_output "$PREFIX/expected.yaml"
}
