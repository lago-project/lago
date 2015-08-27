#!/usr/bin/env bats
LAGOCLI=lagocli
VERBS=(
    cleanup
    copy-from-vm
    copy-to-vm
    init
    ovirt
    shell
    snapshot
    start
    status
    stop
    template-repo
)
FIXTURES="$BATS_TEST_DIRNAME/fixtures/basic"


load helpers
load env_setup


teardown() {
    env_setup.destroy_domains
    env_setup.destroy_nets
}

@test "basic: command shows help" {
    helpers.run \
        "$LAGOCLI" -h
    helpers.equals "$status" '0'
    helpers.contains "$output" 'usage:'
}


@test "basic: command fails and shows help on wrong option" {
    helpers.run \
        "$LAGOCLI" -wrongoption
    ! helpers.equals "$status" '0'
    helpers.contains "$output" 'usage:'
}


@test "basic: make sure all the verbs have help" {
    for verb in "${VERBS[@]}"; do
        if [[ "$verb" == 'shell' ]]; then
            echo "SKIPPING shell, as it does not have help yet"
            continue
        fi
        helpers.run "$LAGOCLI" "$verb" -h
        helpers.equals "$status" '0'
        helpers.contains "$output" 'usage:'
    done
}


@test "basic: full simple run (init, start, status, shell, stop)" {
    local prefix="$FIXTURES"/prefix1
    local repo="$FIXTURES"/repo_store
    local suite="$FIXTURES"/suite.json
    local repo_conf="$FIXTURES"/template_repo.json
    local fake_uuid="12345678910121416182022242628303"
    # INIT
    rm -rf "$prefix" "$repo"
    cp -a "$FIXTURES/repo" "$repo"
    env_setup.populate_disks "$repo"
    export BATS_TMPDIR BATS_TEST_DIRNAME
    # This is needed to be able to run inside mock, as it uses some temp files
    # and that is not seamlesly reachable from out of the chroot by
    # libvirt/kvm
    export LIBGUESTFS_BACKEND=direct
    helpers.run "$LAGOCLI" \
        init \
        --template-repo-path "$repo_conf" \
        --template-repo-name "local_tests_repo" \
        --template-store "$repo" \
        "$prefix" \
        "$suite"
    helpers.equals "$status" '0'
    echo "Checking generated uuid length"
    helpers.equals "$(wc -m "$prefix/uuid")" "32 $prefix/uuid"
    echo "$fake_uuid" > "$prefix/uuid"
    pushd "$prefix" >/dev/null
    # STATUS
    helpers.run "$LAGOCLI" status
    helpers.equals "$status" '0'
    echo "$output" > "$prefix/current"
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT                  | EXPECTED"
    expected_content="$FIXTURES/expected_down_status"
    expected_file="$prefix/expected_down_status"
    sed \
        -e "s|@@BATS_TEST_DIRNAME@@|$BATS_TEST_DIRNAME|g" \
        "$expected_content" \
    > "$expected_file"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "$prefix/current" \
        "$expected_file"
    # START
    helpers.run "$LAGOCLI" start
    helpers.equals "$status" '0'
    # STATUS
    helpers.run "$LAGOCLI" status
    helpers.equals "$status" '0'
    echo "$output" > "$prefix/current"
    # the vnc port is not always 5900, for example, if there's another vm
    # running already
    vnc_port="$(grep -Po '(?<=VNC port: )\d+' "$prefix/current")"
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT                  | EXPECTED"
    expected_content="$FIXTURES/expected_up_status"
    expected_file="$prefix/expected_up_status"
    sed \
        -e "s|@@BATS_TEST_DIRNAME@@|$BATS_TEST_DIRNAME|g" \
        -e "s|@@VNC_PORT@@|${vnc_port:-no port found}|g" \
        "$expected_content" \
    > "$expected_file"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "$prefix/current" \
        "$expected_file"
    # STOP
    helpers.run "$LAGOCLI" stop
    helpers.equals "$status" '0'
}
