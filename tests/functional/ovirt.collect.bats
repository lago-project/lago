#!/usr/bin/env bats
load common
load ovirt_common
load helpers
load env_setup

FIXTURES="$FIXTURES/ovirt.collect"
WORKDIR="$FIXTURES"/.lago


@test "ovirt.collect: setup" {
    # As there's no way to know the last test result, we will handle it here
    local suite="$FIXTURES"/suite.yaml

    rm -rf "$WORKDIR"
    pushd "$FIXTURES"
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    helpers.run_ok "$LAGOCLI" \
        init \
        "$suite"
    helpers.run_ok "$LAGOCLI" start
}


@test "ovirt.collect: generate some logs" {
    common.is_initialized "$WORKDIR" || skip "Workdir not initiated"
    pushd "$FIXTURES"
    outdir="$FIXTURES/output"
    rm -rf "$outdir"
    helpers.run_ok "$LAGOCLI" ovirt deploy
}


@test "ovirt.collect: collect started vms with guest agent" {
    common.is_initialized "$WORKDIR" || skip "Workdir not initiated"
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


@test "ovirt.collect: collect stopped vms" {
    common.is_initialized "$WORKDIR" || skip "Workdir not initiated"
    pushd "$FIXTURES"
    outdir="$FIXTURES/output"
    logfiles=(
        "fancylog.log"
        "fancylog2.log"
    )

    rm -rf "$outdir"
    helpers.run_ok "$LAGOCLI" stop
    helpers.run_ok "$LAGOCLI" ovirt collect --output "$outdir"
    for host in lago_functional_tests_{host,engine}; do
        helpers.is_dir "$outdir/$host"
        if [[ "$host" =~ _host$ ]]; then
            logdir="$outdir/$host/_var_log_vdsm"
        elif [[ "$host" =~ _engine$ ]]; then
            logdir="$outdir/$host/_var_log_ovirt-engine"
        else
            echo "SKIPPING HOST $host"
            continue
        fi
        helpers.is_dir "$logdir"
        for logfile in "${logfiles[@]}"; do
            helpers.is_file "$logdir/$logfile"
            helpers.diff "$FIXTURES/$logfile.expected" "$logdir/$logfile"
        done
    done
}


@test "ovirt.collect: teardown" {
    if common.is_initialized "$WORKDIR"; then
        pushd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" destroy -y
        popd
    fi
    env_setup.destroy_domains
    env_setup.destroy_nets
}
