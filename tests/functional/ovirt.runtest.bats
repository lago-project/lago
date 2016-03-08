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
load ovirt_common
load helpers
load env_setup

FIXTURES="$FIXTURES/ovirt.runtest"
PREFIX="$FIXTURES"/.lago


@test "ovirt.runtest: setup" {
    # As there's no way to know the last test result, we will handle it here
    local suite="$FIXTURES"/suite.yaml

    rm -rf "$PREFIX"
    pushd "$FIXTURES"
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    helpers.run_ok "$LAGOCLI" \
        init \
        "$suite"
    helpers.run_ok "$LAGOCLI" start
}


@test "ovirt.runtest: simple runtest" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"
    testfiles=(
        "001_basic_test.py"
    )

    for testfile in "${testfiles[@]}"; do
        helpers.run_ok "$LAGOCLI" ovirt runtest "$FIXTURES/$testfile"
        helpers.contains "$output" "${testfile%.*}.test_pass"
        helpers.is_file "$PREFIX/nosetests-$testfile.xml"
        helpers.contains \
            "$(cat $PREFIX/nosetests-$testfile.xml)" \
            'errors="0"'
    done
}


@test "ovirt.runtest: failing a test fails the run" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"
    testfiles=(
        "001_basic_failed_test.py"
    )

    for testfile in "${testfiles[@]}"; do
        helpers.run_nook "$LAGOCLI" ovirt runtest "$FIXTURES/$testfile"
        helpers.contains "$output" "${testfile%.*}.test_fail"
        helpers.is_file "$PREFIX/nosetests-$testfile.xml"
        helpers.contains \
            "$(cat $PREFIX/nosetests-$testfile.xml)" \
            'failures="1"'
    done
}


@test "ovirt.runtest: error in a test fails the run" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"
    testfiles=(
        "001_basic_errored_test.py"
    )

    for testfile in "${testfiles[@]}"; do
        helpers.run_nook "$LAGOCLI" ovirt runtest "$FIXTURES/$testfile"
        helpers.contains "$output" "${testfile%.*}.test_error"
        helpers.is_file "$PREFIX/nosetests-$testfile.xml"
        helpers.contains \
            "$(cat $PREFIX/nosetests-$testfile.xml)" \
            'errors="1"'
    done
}


@test "ovirt.runtest: teardown" {
    if common.is_initialized "$PREFIX"; then
        pushd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" destroy -y
        popd
    fi
    env_setup.destroy_domains
    env_setup.destroy_nets
}
