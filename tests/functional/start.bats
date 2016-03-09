#!/usr/bin/env bats
load common
load helpers
load env_setup


LIBVIRT_PREFIX="lft_"
FIXTURES="$FIXTURES/start"
WORKDIR="$FIXTURES"/.lago
REPO_STORE="$FIXTURES"/repo_store
STORE="$FIXTURES"/store
REPO_CONF="$FIXTURES"/template_repo.json
REPO_NAME="local_tests_repo"


@test "start: init" {
    local suite="$FIXTURES"/1vm_bridged.json

    rm -rf "$WORKDIR" "$STORE"

    # This is needed to be able to run inside mock, as it uses some temp files
    # and that is not seamlesly reachable from out of the chroot by
    # libvirt/kvm
    export BATS_TMPDIR BATS_TEST_DIRNAME
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    cd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" \
        init \
        --template-repo-path "$REPO_CONF" \
        --template-repo-name "$REPO_NAME" \
        --template-store "$STORE" \
        "$suite"
    # This is needed to be able to run sudo inside the chroot
    echo 'Defaults:root !requiretty' > /etc/sudoers.d/lago_functional_tests
}


@test "start.1vm_bridged: start everything at once" {
    common.is_initialized "$WORKDIR" || skip "Workdir not initiated"
    cd "$FIXTURES"

    helpers.run_ok "$LAGOCLI" start
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/expected_up_status"
}


@test "start.1vm_bridged: start is reentrant" {
    # As there's no way to know the last test result, we will handle it here
    common.is_initialized "$WORKDIR" || skip "Workdir not initiated"
    cd "$FIXTURES"

    helpers.run_ok "$LAGOCLI" start
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/expected_up_status"
}


@test "start: teardown" {
    common.is_initialized "$WORKDIR" \
    common.is_initialized "$prefix" \
    && {
        cd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" cleanup
    }
    env_setup.destroy_domains "$LIBVIRT_PREFIX"
    env_setup.destroy_nets "$LIBVIRT_PREFIX"
}
