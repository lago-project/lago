#!/usr/bin/env bats
load common
load helpers
load env_setup

FIXTURES="$FIXTURES/snapshot"
WORKDIR="$FIXTURES"/.lago

unset LAGO__START__WAIT_SUSPEND

@test "snapshot.1host_1disk: setup" {
    # As there's no way to know the last test result, we will handle it here
    local suite="$FIXTURES"/suite_1host_1disk.yaml

    rm -rf "$WORKDIR"
    pushd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" \
        init \
        "$suite"
    helpers.run_ok "$LAGOCLI" start
}


@test "snapshot.1host_1disk: take live snapshot" {
    common.is_initialized "$WORKDIR" || skip "prefix not initiated"
    pushd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" start
    helpers.run_ok "$LAGOCLI" shell "lago_functional_tests_vm01" <<EOC
        echo "content before tests" > /root/nicefile
        sync
EOC
    helpers.run_ok "$LAGOCLI" snapshot 'snapshot_number_1'
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/1host_1disk_status"
}


@test "snapshot.1host_1disk: list snapshot" {
    common.is_initialized "$WORKDIR" || skip "prefix not initiated"
    pushd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" --out-format json snapshot --list
    helpers.diff_output "$FIXTURES/1host_1disk_list"
}


@test "snapshot.1host_1disk: make a change" {
    common.is_initialized "$WORKDIR" || skip "prefix not initiated"
    pushd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" shell "lago_functional_tests_vm01" <<EOC
        echo "content after tests" > /root/nicefile
        sync
EOC
    helpers.run_ok "$LAGOCLI" \
        copy-from-vm \
        'lago_functional_tests_vm01' \
        '/root/nicefile' \
        "$WORKDIR"/nicefile
    helpers.run_ok echo -e "content after tests"
    helpers.diff_output "$WORKDIR"/nicefile
    rm -f "$WORKDIR"/nicefile
}


@test "snapshot.1host_1disk: revert" {
    common.is_initialized "$WORKDIR" || skip "prefix not initiated"
    pushd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" revert 'snapshot_number_1'
    helpers.run_ok "$LAGOCLI" \
        copy-from-vm \
        'lago_functional_tests_vm01' \
        '/root/nicefile' \
        "$WORKDIR"/nicefile
    helpers.run_ok echo -e "content before tests"
    helpers.diff_output "$WORKDIR"/nicefile
}


@test "snapshot.1host_1disk: teardown" {
    if common.is_initialized "$WORKDIR"; then
        pushd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" destroy -y --all-prefixes
        popd
    fi
    env_setup.destroy_domains
    env_setup.destroy_nets
}
