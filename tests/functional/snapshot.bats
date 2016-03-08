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

FIXTURES="$FIXTURES/snapshot"
PREFIX="$FIXTURES"/.lago


@test "snapshot.1host_1disk: setup" {
    # As there's no way to know the last test result, we will handle it here
    local suite="$FIXTURES"/suite_1host_1disk.yaml

    rm -rf "$PREFIX"
    pushd "$FIXTURES"
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    helpers.run_ok "$LAGOCLI" \
        init \
        "$suite"
    helpers.run_ok "$LAGOCLI" start
}


@test "snapshot.1host_1disk: take live snapshot" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" start
    helpers.run_ok "$LAGOCLI" shell "lago_functional_tests_vm01" <<EOC
        echo "content before tests" > /root/nicefile
EOC
    helpers.run_ok "$LAGOCLI" snapshot 'snapshot_number_1'
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/1host_1disk_status"
}


@test "snapshot.1host_1disk: list snapshot" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" --out-format json snapshot --list
    helpers.diff_output "$FIXTURES/1host_1disk_list"
}


@test "snapshot.1host_1disk: make a change" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" shell "lago_functional_tests_vm01" <<EOC
        echo "content after tests" > /root/nicefile
EOC
    helpers.run_ok "$LAGOCLI" \
        copy-from-vm \
        'lago_functional_tests_vm01' \
        '/root/nicefile' \
        "$PREFIX"/nicefile
    helpers.run_ok echo -e "\ncontent after tests"
    helpers.diff_output "$PREFIX"/nicefile
    rm -f "$PREFIX"/nicefile
}


@test "snapshot.1host_1disk: revert" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" revert 'snapshot_number_1'
    helpers.run_ok "$LAGOCLI" \
        copy-from-vm \
        'lago_functional_tests_vm01' \
        '/root/nicefile' \
        "$PREFIX"/nicefile
    helpers.run_ok echo -e "\ncontent before tests"
    helpers.diff_output "$PREFIX"/nicefile
}


@test "snapshot.1host_1disk: teardown" {
    if common.is_initialized "$PREFIX"; then
        pushd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" destroy -y
        popd
    fi
    env_setup.destroy_domains
    env_setup.destroy_nets
}
