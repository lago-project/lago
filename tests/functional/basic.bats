#!/usr/bin/env bats
load common
load helpers
load env_setup

FIXTURES="$FIXTURES/basic"


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
    local prefix="$FIXTURES"/prefix1
    local repo="$FIXTURES"/repo_store

    rm -rf "$prefix" "$repo"
    cp -a "$FIXTURES/repo" "$repo"
    env_setup.populate_disks "$repo"
}


@test "basic.full_run: init" {
    local prefix="$FIXTURES"/prefix1
    local repo="$FIXTURES"/repo_store
    local suite="$FIXTURES"/suite.json
    local repo_conf="$FIXTURES"/template_repo.json

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
}


@test "basic.full_run: checking uuid and replacing with mocked one" {
    local prefix="$FIXTURES"/prefix1
    local fake_uuid="12345678910121416182022242628303"

    echo "Checking generated uuid length"
    helpers.equals "$(wc -m "$prefix/uuid")" "32 $prefix/uuid"
    echo "$fake_uuid" > "$prefix/uuid"
}


@test "basic.full_run: status when stopped" {
    local prefix="$FIXTURES"/prefix1

    common.is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
    helpers.run_ok "$LAGOCLI" status
    echo "$output" \
    | tail -n+2 \
    > "$prefix/current"
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT                  | EXPECTED"
    expected_content="$FIXTURES/expected_down_status"
    expected_file="expected_down_status"
    sed \
        -e "s|@@BATS_TEST_DIRNAME@@|$BATS_TEST_DIRNAME|g" \
        "$expected_content" \
    > "$expected_file"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "current" \
        "$expected_file"
}


@test "basic.full_run: status when stopped explicitly specifying the prefix" {
    local prefix="$FIXTURES"/prefix1

    common.is_initialized "$prefix" || skip "prefix not initiated"
    helpers.run_ok "$LAGOCLI" --prefix-path "$prefix" status
    echo "$output" \
    | tail -n+2 \
    > "$prefix/current"
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT                  | EXPECTED"
    expected_content="$FIXTURES/expected_down_status"
    expected_file="expected_down_status"
    sed \
        -e "s|@@BATS_TEST_DIRNAME@@|$BATS_TEST_DIRNAME|g" \
        "$expected_content" \
    > "$expected_file"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "$prefix/current" \
        "$expected_file"
}



@test "basic.full_run: start everything at once" {
    local prefix="$FIXTURES"/prefix1

    common.is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
    helpers.run_ok "$LAGOCLI" start
}


@test "basic.full_run: status when started" {
    local prefix="$FIXTURES"/prefix1

    common.is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
    helpers.run_ok "$LAGOCLI" status
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


@test "basic.full_run: shell to a vm" {
    local prefix="$FIXTURES"/prefix1
    local expected_hostname="cirros"

    common.is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
    helpers.run_ok "$LAGOCLI" shell "lago_functional_tests_vm01" hostname
    output="$(echo "$output"| tail -n1)"
    helpers.contains "$output" "$expected_hostname"
}


@test "basic.full_run: copy to vm" {
    local prefix="$FIXTURES"/prefix1

    common.is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
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
    local prefix="$FIXTURES"/prefix1

    common.is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
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
    local prefix="$FIXTURES"/prefix1

    common.is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$prefix" >/dev/null
    helpers.run_ok "$LAGOCLI" stop
    # STATUS
    helpers.run_ok "$LAGOCLI" status
    echo "$output" \
    | tail -n+2 \
    > "$prefix/current"
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
}


@test "basic.full_run: destroy" {
    local prefix="$FIXTURES"/prefix1
    local prefix_link="$FIXTURES"/.lago

    common.is_initialized "$prefix" || skip "prefix not initiated"
    pushd "$FIXTURES" >/dev/null
    ln -s "$prefix" "$prefix_link"
    echo "Destroying the link-based prefix"
    helpers.run_ok "$LAGOCLI" destroy --yes
    helpers.not_exists "$prefix_link"

    echo "Destroying from inside the prefix"
    helpers.is_dir "$prefix"
    pushd "$prefix" >/dev/null
    common.initialize "$prefix"
    helpers.run_ok "$LAGOCLI" --loglevel debug --logdepth -1 destroy --yes
    helpers.not_exists "$prefix"
}



@test 'basic.full_run: start and stop many vms one by one' {
    local basedir="$FIXTURES/basedir"
    local repo="$FIXTURES"/repo_store
    local suite="$FIXTURES"/suite2.yaml
    local repo_conf="$FIXTURES"/template_repo.json
    local fake_uuid="12345678910121416182022242628303"
    PREFIX_PATH="$basedir/.lago"
    # INIT
    rm -rf "$basedir" "$repo"
    mkdir -p "$basedir/extradir"
    cp -a "$FIXTURES/repo" "$repo"
    env_setup.populate_disks "$repo"
    export BATS_TMPDIR BATS_TEST_DIRNAME
    # This is needed to be able to run inside mock, as it uses some temp files
    # and that is not seamlesly reachable from out of the chroot by
    # libvirt/kvm
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    cd "$basedir"
    helpers.run_ok "$LAGOCLI" \
        init \
        --template-repo-path "$repo_conf" \
        --template-repo-name "local_tests_repo" \
        --template-store "$repo" \
        "$suite"
    echo "Checking generated uuid length"
    helpers.equals "$(wc -m ".lago/uuid")" "32 .lago/uuid"
    echo "$fake_uuid" > ".lago/uuid"
    # make sure that the prefix recursive find works
    cd extradir
    # START vm02
    helpers.run_ok "$LAGOCLI" start lago_functional_tests_vm02
    # STATUS
    helpers.run_ok "$LAGOCLI" status
    echo "$output" \
    | tail -n+2 \
    > "current"
    # the vnc port is not always 5900, for example, if there's another vm
    # running already
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT                  | EXPECTED"
    expected_content="$FIXTURES/expected2_down_status_vm01"
    expected_file="expected2_down_status_vm01"
    sed \
        -e "s|@@PREFIX_PATH@@|$PREFIX_PATH|g" \
        "$expected_content" \
    | grep -v 'VNC port' \
    > "$expected_file"
    grep -v 'VNC port' "current" \
    > "current.now"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "current.now" \
        "$expected_file"
    # START vm01
    helpers.run_ok "$LAGOCLI" start lago_functional_tests_vm01
    # STATUS
    helpers.run_ok "$LAGOCLI" status
    echo "$output" \
    | tail -n+2 \
    > "current"
    # the vnc port is not always 5900, for example, if there's another vm
    # running already
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT                  | EXPECTED"
    expected_content="$FIXTURES/expected2_up_status_all"
    expected_file="expected2_up_status_all"
    sed \
        -e "s|@@PREFIX_PATH@@|$PREFIX_PATH|g" \
        "$expected_content" \
    | grep -v 'VNC port' \
    > "$expected_file"
    grep -v 'VNC port' "current" \
    > "current.now"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "current.now" \
        "$expected_file"
    # STOP vm02
    helpers.run_ok "$LAGOCLI" stop lago_functional_tests_vm02
    # STATUS
    helpers.run_ok "$LAGOCLI" status
    echo "$output" \
    | tail -n+2 \
    > "current"
    # the vnc port is not always 5900, for example, if there's another vm
    # running already
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT                  | EXPECTED"
    expected_content="$FIXTURES/expected2_up_status_vm01"
    expected_file="expected2_up_status_vm01"
    sed \
        -e "s|@@PREFIX_PATH@@|$PREFIX_PATH|g" \
        "$expected_content" \
    | grep -v 'VNC port' \
    > "$expected_file"
    grep -v 'VNC port' "current" \
    > "current.now"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "current.now" \
        "$expected_file"
    # STOP vm01
    helpers.run_ok "$LAGOCLI" stop lago_functional_tests_vm01
    # STATUS
    helpers.run_ok "$LAGOCLI" status
    echo "$output" \
    | tail -n+2 \
    > "current"
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT                  | EXPECTED"
    expected_content="$FIXTURES/expected2_down_status_all"
    expected_file="expected2_down_status_all"
    sed \
        -e "s|@@PREFIX_PATH@@|$PREFIX_PATH|g" \
        "$expected_content" \
    | grep -v 'VNC port' \
    > "$expected_file"
    grep -v 'VNC port' "current" \
    > "current.now"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "current.now" \
        "$expected_file"
}


@test "basic.full_run: start again" {
    local basedir="$FIXTURES/basedir"
    local prefix="$basedir"/.lago

    common.is_initialized "$prefix" || skip "prefix not initiated"
    cd "$basedir"
    helpers.run_ok "$LAGOCLI" start
}


@test "basic.full_run: cleanup a started prefix" {
    local basedir="$FIXTURES/basedir"
    local prefix="$basedir"/.lago

    common.is_initialized "$prefix" || skip "prefix not initiated"
    cd "$basedir"
    helpers.run_ok "$LAGOCLI" cleanup
    helpers.contains "$output" "Stop prefix"
    helpers.is_file "$prefix/uuid"
    ! common.is_initialized "$prefix"
}


@test "basic.full_run: reinitialize and start again" {
    local basedir="$FIXTURES/basedir"
    local prefix="$basedir"/.lago

    common.initialize "$prefix"
    cd "$basedir"
    helpers.run_ok "$LAGOCLI" start
}


@test "basic.full_run: destroy a started prefix" {
    local basedir="$FIXTURES/basedir"
    local prefix="$basedir"/.lago

    common.is_initialized "$prefix" || skip "prefix not initiated"
    cd "$basedir"
    helpers.run_ok "$LAGOCLI" destroy --yes
    helpers.contains "$output" "Stop prefix"
    helpers.not_exists "$prefix"
}


@test "basic: teardown" {
    env_setup.destroy_domains
    env_setup.destroy_nets
}

