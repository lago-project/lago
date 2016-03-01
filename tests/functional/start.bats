#!/usr/bin/env bats
load common
load helpers
load env_setup


LIBVIRT_PREFIX="lft_"
FIXTURES="$FIXTURES/start"


@test "start: init" {
    local prefix="$FIXTURES"/prefix1
    local repo="$FIXTURES"/repo_store
    local suite="$FIXTURES"/1vm_bridged.json
    local repo_conf="$FIXTURES"/template_repo.json
    local fake_uuid="12345678910121416182022242628303"

    rm -rf "$prefix" "$repo"

    # This is needed to be able to run inside mock, as it uses some temp files
    # and that is not seamlesly reachable from out of the chroot by
    # libvirt/kvm
    export BATS_TMPDIR BATS_TEST_DIRNAME
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    helpers.run_ok "$LAGOCLI" \
        init \
        --template-repo-path "$repo_conf" \
        --template-repo-name "local_tests_repo" \
        --template-store "$repo" \
        "$prefix" \
        "$suite"

    echo "$fake_uuid" > "$prefix/uuid"
}


@test "start.1vm_bridged: start everything at once" {
    local prefix="$FIXTURES"/prefix1

    common.is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
    helpers.run_ok "$LAGOCLI" start

    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/expected_up_status"
}


@test "start.1vm_bridged: start is reentrant" {
    # As there's no way to know the last test result, we will handle it here
    local prefix="$FIXTURES"/prefix1
    local repo="$FIXTURES"/repo_store

    common.is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
    helpers.run_ok "$LAGOCLI" start

    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/expected_up_status"
}


@test "start: teardown" {
    local prefix="$FIXTURES"/prefix1

    common.is_initialized "$prefix" \
    && {
        pushd "$prefix" >/dev/null
        helpers.run_ok "$LAGOCLI" cleanup
    }

    env_setup.destroy_domains "$LIBVIRT_PREFIX"
    env_setup.destroy_nets "$LIBVIRT_PREFIX"
}

