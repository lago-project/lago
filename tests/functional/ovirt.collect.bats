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

FIXTURES="$FIXTURES/ovirt.collect"
PREFIX="$FIXTURES"/.lago


@test "ovirt.collect: setup" {
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


@test "ovirt.collect: generate some logs" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"
    outdir="$FIXTURES/output"
    rm -rf "$outdir"
    helpers.run_ok "$LAGOCLI" ovirt deploy
}


@test "ovirt.collect: collect" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"
    outdir="$FIXTURES/output"
    logfiles=(
        "fancylog.log"
        "fancylog2.log"
    )

    rm -rf "$outdir"
    helpers.run_ok "$LAGOCLI" ovirt collect --output "$outdir"
    for host in lago_functional_tests_{host,engine}; do
        helpers.is_dir "$outdir/$host"
        if [[ "$host" =~ _host$ ]]; then
            logdir="$outdir/$host/_var_log_vdsm"
            remote_logdir="/var/log/vdsm"
        elif [[ "$host" =~ _engine$ ]]; then
            logdir="$outdir/$host/_var_log_ovirt-engine"
            remote_logdir="/var/log/ovirt-engine"
        else
            echo "SKIPPING HOST $host"
            continue
        fi
        helpers.is_dir "$logdir"
        for logfile in "${logfiles[@]}"; do
            helpers.is_file "$logdir/$logfile"
            helpers.run_ok "$LAGOCLI" \
                shell "$host" \
                cat "$remote_logdir/$logfile"
            helpers.diff_output "$logdir/$logfile"
        done
    done
}


@test "ovirt.collect: teardown" {
    if common.is_initialized "$PREFIX"; then
        pushd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" destroy -y
        popd
    fi
    env_setup.destroy_domains
    env_setup.destroy_nets
}
