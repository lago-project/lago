#!/usr/bin/env bats
load common
load helpers
load env_setup

FIXTURES="$FIXTURES/basic"
CUSTOM_WORKDIR="$FIXTURES/workdir"
WORKDIR="$FIXTURES/.lago"
PREFIX_NAMES=(
    prefix1
    prefix2
)
REPO_STORE="$FIXTURES"/repo_store
STORE="$FIXTURES"/store
REPO_CONF="$FIXTURES"/template_repo.json
REPO_NAME="local_tests_repo"


@test "basic: command shows help" {
    helpers.run_ok \
        "$LAGOCLI" -h
    helpers.contains "$output" 'usage:'
}


@test "basic: command shows version" {
    installed_version="$(rpm -qa lago --queryformat %{version})"
    helpers.run_ok \
        "$LAGOCLI" --version
    helpers.contains "$output" "lago $installed_version"
}


@test "basic: lago and lagocli are both accepted" {
    helpers.run_ok \
        "lago" -h
    helpers.contains "$output" 'usage:'
    helpers.run_ok \
        "lagocli" -h
    helpers.contains "$output" 'usage:'
}


@test "basic: command fails and shows help on wrong option" {
    helpers.run_nook \
        "$LAGOCLI" -wrongoption
    helpers.contains "$output" 'usage:'
}


@test "basic: make sure all the verbs have help" {
    for verb in "${VERBS[@]}"; do
        if [[ "$verb" == 'shell' ]]; then
            echo "SKIPPING shell, as it does not have help yet"
            continue
        fi
        helpers.run_ok "$LAGOCLI" "$verb" -h
        helpers.contains "$output" 'usage:'
    done
}


@test "basic.full_run: preparing full simple run" {
    # As there's no way to know the last test result, we will handle it here
    rm -rf "$REPO_STORE" "$WORKDIR"
    cp -a "$FIXTURES/store_skel" "$REPO_STORE"
    env_setup.populate_disks "$REPO_STORE"
}


@test "basic.full_run: init workdir with default prefix" {
    local workdir="$FIXTURES"/workdir
    local suite="$FIXTURES"/suite.json

    # This is needed to be able to run inside mock, as it uses some temp files
    # and that is not seamlesly reachable from out of the chroot by
    # libvirt/kvm
    export BATS_TMPDIR BATS_TEST_DIRNAME
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    helpers.run_ok "$LAGOCLI" \
        init \
        --template-repo-path "$REPO_CONF" \
        --template-repo-name "$REPO_NAME" \
        --template-store "$STORE" \
        "$WORKDIR" \
        "$suite"
    helpers.is_dir "$WORKDIR/default"
    helpers.links_to "$WORKDIR/current" "default"
}


@test "basic.full_run: init workdir with extra prefixes" {
    local workdir="$FIXTURES"/workdir
    local suite="$FIXTURES"/suite.json

    # This is needed to be able to run inside mock, as it uses some temp files
    # and that is not seamlesly reachable from out of the chroot by
    # libvirt/kvm
    export BATS_TMPDIR BATS_TEST_DIRNAME
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    cd "$FIXTURES"
    for prefix_name in "${PREFIX_NAMES[@]}"; do
        echo "Creating prefix $prefix_name in $WORKDIR"
        helpers.run_ok "$LAGOCLI" \
            --prefix-name "$prefix_name" \
            init \
            --template-repo-path "$REPO_CONF" \
            --template-repo-name "$REPO_NAME" \
            --template-store "$STORE" \
            "$suite"
        helpers.is_dir "$WORKDIR/$prefix_name"
        helpers.links_to "$WORKDIR/current" "default"
    done
}


@test "basic.full_run: current prefix status when stopped" {
    common.is_initialized "$WORKDIR" || skip "Workdir not initiated"
    helpers.run_ok "$LAGOCLI" --workdir "$WORKDIR" status
    helpers.diff_output "$FIXTURES/expected_down_status"
}


@test "basic.full_run: ignore-warnings hides the group warning" {
    common.is_initialized "$WORKDIR" || skip "Workdir not initiated"
    helpers.run_ok "$LAGOCLI" --ignore-warnings --workdir "$WORKDIR" status
    helpers.diff_output_nowarning "$FIXTURES/expected_down_status"
}



@test "basic.full_run: explicit prefix name status when stopped" {
    common.is_initialized "$WORKDIR" || skip "Workdir not initiated"
    cd "$FIXTURES"
    for PREFIX_NAME in 'default' "${PREFIX_NAMES[@]}"; do
        PREFIX="$WORKDIR"/"$PREFIX_NAME"
        helpers.run_ok "$LAGOCLI" \
            --prefix-name "$PREFIX_NAME"\
            status
        helpers.diff_output "$FIXTURES/expected_down_status"
    done
}


@test "basic.full_run: (to be deprecated) status when stopped explicitly specifying the prefix" {
    PREFIX="$WORKDIR/${PREFIX_NAMES[0]}"
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    cd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" --prefix-path "$PREFIX" status
    helpers.diff_output "$FIXTURES/expected_down_status"
}


@test "basic.full_run: start everything at once" {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" start
}


@test "basic.full_run: status when started" {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/expected_up_status"
}


@test "basic.full_run: shell to a vm" {
    local expected_hostname="cirros"
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" shell "lago_functional_tests_vm01" hostname
    output="$(echo "$output"| tail -n1)"
    helpers.contains "$output" "$expected_hostname"
}


@test "basic.full_run: copy to vm" {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    rm -rf dummy_file
    content="$(date)"
    echo "$content" > "dummy_file"
    helpers.run_ok "$LAGOCLI" \
        copy-to-vm \
        "lago_functional_tests_vm01" \
        dummy_file \
        /root/dummy_file_inside
    helpers.run_ok "$LAGOCLI" \
        shell \
        "lago_functional_tests_vm01" \
        cat /root/dummy_file_inside
    output="$(echo "$output"| tail -n1)"
    helpers.contains "$output" "$content"
}


@test "basic.full_run: copy from vm" {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    rm -rf dummy_file
    content="$(date)"
    helpers.run_ok "$LAGOCLI" \
        shell \
        "lago_functional_tests_vm01" \
        <<EOS
          echo "$content" > /root/dummy_file_inside
EOS
    helpers.run_ok "$LAGOCLI" \
        copy-from-vm \
        "lago_functional_tests_vm01" \
        /root/dummy_file_inside \
        dummy_file
    output="$(cat dummy_file)"
    helpers.contains "$output" "$content"
}


@test "basic.full_run: whole stop" {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" stop
    # STATUS
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/expected_down_status"
}


@test "basic.full_run: destroying a soft linked workdir only removes the link" {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    local workdir_link="$FIXTURES"/workdir_link
    ln -s "$WORKDIR" "$workdir_link"
    helpers.run_ok \
        "$LAGOCLI" \
        --workdir "$workdir_link" \
        destroy --yes --all-prefixes
    helpers.not_exists "$workdir_link"
    helpers.is_dir "$WORKDIR"
}


@test "basic.full_run: destroy a prefix from inside" {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    local prefix="$WORKDIR/${PREFIX_NAMES[0]}"
    common.is_initialized "$prefix" || skip "prefix $prefix not initiated"
    cd "$prefix"
    helpers.run_ok \
        "$LAGOCLI" \
        --loglevel debug \
        --logdepth -1 \
        destroy --yes
    helpers.not_exists "$prefix"
    helpers.is_dir "$WORKDIR"
}


@test 'basic.full_run: start and stop many vms one by one' {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    local PREFIX_NAME='multi_vm'
    local suite="$FIXTURES"/suite_multi_vm.yaml
    # INIT
    rm -rf "$WORKDIR/$PREFIX_NAME"
    export BATS_TMPDIR BATS_TEST_DIRNAME
    # This is needed to be able to run inside mock, as it uses some temp files
    # and that is not seamlesly reachable from out of the chroot by
    # libvirt/kvm
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    helpers.run_ok "$LAGOCLI" \
        --prefix-name "$PREFIX_NAME" \
        init \
        --template-repo-path "$REPO_CONF" \
        --template-repo-name "$REPO_NAME" \
        --template-store "$REPO_STORE" \
        "$suite"

    # Set as current prefix
    helpers.run_ok "$LAGOCLI" set-current "$PREFIX_NAME"
    helpers.links_to "$WORKDIR/current" "$PREFIX_NAME"
    # START vm02
    helpers.run_ok "$LAGOCLI" start lago_functional_tests_vm02
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/expected2_down_status_vm01"
    # START vm01
    helpers.run_ok "$LAGOCLI" start lago_functional_tests_vm01
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/expected2_up_status_all"
    # STOP vm02
    helpers.run_ok "$LAGOCLI" stop lago_functional_tests_vm02
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/expected2_up_status_vm01"
    # STOP vm01
    helpers.run_ok "$LAGOCLI" stop lago_functional_tests_vm01
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$FIXTURES/expected2_down_status_all"
}


@test "basic.full_run: start again" {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    local PREFIX_NAME='multi_vm'
    helpers.run_ok "$LAGOCLI" --prefix-name "$PREFIX_NAME" start
}


@test "basic.full_run: cleanup a started prefix" {
    local PREFIX_NAME='multi_vm'

    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" --prefix-name "$PREFIX_NAME" cleanup
    helpers.contains "$output" "Stop prefix"
    helpers.is_file "$WORKDIR/$PREFIX_NAME/uuid"
    ! common.is_initialized "$WORKDIR/$PREFIX_NAME"
}


@test "basic.full_run: reinitialize and start again" {
    local PREFIX_NAME='multi_vm'

    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    common.initialize "$WORKDIR/$PREFIX_NAME"
    helpers.run_ok "$LAGOCLI" --prefix-name "$PREFIX_NAME" start
}


@test "basic.full_run: destroy a started prefix" {
    local PREFIX_NAME='multi_vm'

    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" --prefix-name "$PREFIX_NAME" destroy --yes
    helpers.contains "$output" "Stop prefix"
    helpers.not_exists "$WORKDIR/$PREFIX_NAME"
}


@test "basic.full_run: destroy all the prefixes" {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" destroy --yes --all-prefixes
    helpers.contains "$output" "Stop prefix"
    helpers.not_exists "$WORKDIR"
}


@test "basic: teardown" {
    env_setup.destroy_domains
    env_setup.destroy_nets
}
