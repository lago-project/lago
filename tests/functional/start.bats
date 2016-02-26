#!/usr/bin/env bats
LAGOCLI=lagocli
FIXTURES="$BATS_TEST_DIRNAME/fixtures/start"
LIBVIRT_PREFIX="lft_"


load helpers
load env_setup


is_initialized() {
    local prefix="${1?}"
    [[ -e "$prefix/initialized" ]]
    return $?
}


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
    helpers.run "$LAGOCLI" \
        init \
        --template-repo-path "$repo_conf" \
        --template-repo-name "local_tests_repo" \
        --template-store "$repo" \
        "$prefix" \
        "$suite"
    helpers.equals "$status" '0'

    echo "$fake_uuid" > "$prefix/uuid"
}


@test "start.1vm_bridged: start everything at once" {
    local prefix="$FIXTURES"/prefix1

    is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
    helpers.run "$LAGOCLI" start
    helpers.equals "$status" '0'

    helpers.run "$LAGOCLI" status
    helpers.equals "$status" '0'
    echo "$output" \
    | tail -n+2 \
    > "$prefix/current"
    # the vnc port is not always 5900, for example, if there's another vm
    # running already
    echo "Extracting vnc port from the current status"
    vnc_port="$(grep -Po '(?<=VNC port: )\d+' "$prefix/current")" || :
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT                  | EXPECTED"
    expected_content="$FIXTURES/expected_up_status"
    expected_file="expected_up_status"
    sed \
        -e "s|@@BATS_TEST_DIRNAME@@|$BATS_TEST_DIRNAME|g" \
        -e "s|@@VNC_PORT@@|${vnc_port:-no port found}|g" \
        "$expected_content" \
    > "$expected_file"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "current" \
        "$expected_file"
}


@test "start.1vm_bridged: start is reentrant" {
    # As there's no way to know the last test result, we will handle it here
    local prefix="$FIXTURES"/prefix1
    local repo="$FIXTURES"/repo_store

    is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
    helpers.run "$LAGOCLI" start
    helpers.equals "$status" '0'

    helpers.run "$LAGOCLI" status
    helpers.equals "$status" '0'
    echo "$output" \
    | tail -n+2 \
    > "$prefix/current"
    # the vnc port is not always 5900, for example, if there's another vm
    # running already
    echo "Extracting vnc port from the current status"
    vnc_port="$(grep -Po '(?<=VNC port: )\d+' "$prefix/current")" || :
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT                  | EXPECTED"
    expected_content="$FIXTURES/expected_up_status"
    expected_file="expected_up_status"
    sed \
        -e "s|@@BATS_TEST_DIRNAME@@|$BATS_TEST_DIRNAME|g" \
        -e "s|@@VNC_PORT@@|${vnc_port:-no port found}|g" \
        "$expected_content" \
    > "$expected_file"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "current" \
        "$expected_file"
}


@test "start: teardown" {
    local prefix="$FIXTURES"/prefix1

    is_initialized "$prefix" \
    && {
        pushd "$prefix" >/dev/null
        helpers.run "$LAGOCLI" cleanup
    }

    env_setup.destroy_domains "$LIBVIRT_PREFIX"
    env_setup.destroy_nets "$LIBVIRT_PREFIX"
}

