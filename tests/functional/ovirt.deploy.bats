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

FIXTURES="$FIXTURES/ovirt.deploy"
PREFIX="$FIXTURES"/.lago


@test "ovirt.deploy.basic: setup" {
    # As there's no way to know the last test result, we will handle it here
    local suite="$FIXTURES"/suite_1host.yaml

    rm -rf "$PREFIX"
    pushd "$FIXTURES"
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    helpers.run_ok "$LAGOCLI" \
        init \
        "$suite"
    helpers.run_ok "$LAGOCLI" start
}


@test "ovirt.deploy.basic: deploy" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"

    helpers.run_ok "$LAGOCLI" ovirt deploy

echo "Checking that the nicefile was properly created"
    helpers.run_ok "$LAGOCLI" shell 'lago_functional_tests_vm01' <<EOC
    cat /root/nicefile
EOC
    helpers.diff_output "$FIXTURES/nicefile"

    echo "Checking that the uglyfile was properly created"
    helpers.run_ok "$LAGOCLI" shell 'lago_functional_tests_vm01' <<EOC
    cat /root/uglyfile
EOC
    helpers.diff_output "$FIXTURES/uglyfile"
}


@test "ovirt.deploy.basic: teardown" {
    if common.is_initialized "$PREFIX"; then
        pushd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" destroy -y
        popd
    fi
    env_setup.destroy_domains
    env_setup.destroy_nets
}


@test "ovirt.deploy.fail_on_deploy_failure: setup" {
    # As there's no way to know the last test result, we will handle it here
    local suite="$FIXTURES"/suite_1host_fail.yaml

    rm -rf "$PREFIX"
    pushd "$FIXTURES"
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    helpers.run_ok "$LAGOCLI" \
        init \
        "$suite"
    helpers.run_ok "$LAGOCLI" start
}


@test "ovirt.deploy.fail_on_deploy_failure: failed deploy" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"

    helpers.run_nook "$LAGOCLI" --loglevel debug ovirt deploy
    helpers.contains "$output" "I'm going to fail"
}


@test "ovirt.deploy.fail_on_deploy_failure: teardown" {
    if common.is_initialized "$PREFIX"; then
        pushd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" destroy -y
        popd
    fi
    env_setup.destroy_domains
    env_setup.destroy_nets
}

