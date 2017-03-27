#!/usr/bin/env bats -x
load common
load helpers
load env_setup

FIXTURES="$FIXTURES/export"
CUSTOM_WORKDIR="$FIXTURES/workdir"
WORKDIR="$FIXTURES/.lago"

REPO_STORE="$FIXTURES"/repo_store
STORE="$FIXTURES"/store
REPO_CONF="$FIXTURES"/template_repo.json
REPO_NAME="local_tests_repo"
VM_NAME=lago_functional_tests_vm01

SA_ENV="sa_exported_env"
LAYERED_ENV="layered_exported_env"
STAND_ALONE_EXPORT_DIR="${FIXTURES}/${SA_ENV}"
LAYERED_EXPORT_DIR="${FIXTURES}/${LAYERED_ENV}"

# needed in order to run libguestfs inside mock
export LIBGUESTFS_BACKEND=direct

@test "export.init" {
    local workdir="$FIXTURES"/workdir
    local suite="$FIXTURES"/suite.json

    rm -rf "$WORKDIR" "$STORE"

    # This is needed to be able to run inside mock, as it uses some temp files
    # and that is not seamlesly reachable from out of the chroot by
    # libvirt/kvm
    export BATS_TMPDIR BATS_TEST_DIRNAME
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

@test "export.start: start everything at once" {
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    cd "$FIXTURES"
    helpers.run_ok "$LAGOCLI" start
}

@test "export.place_dummy_file" {
    cd $FIXTURES
    rm -rf dummy_file

    local content="$(date)"
    echo "$content" > "dummy_file"

    helpers.run_ok "$LAGOCLI" \
        copy-to-vm \
        "$VM_NAME" \
        dummy_file \
        /root/dummy_file_inside

    # Just to be sure that the file was written to disk
    sleep 2
}

@test "export.fail_to_export_running_env" {
    cd "$FIXTURES"

    helpers.run_nook "$LAGOCLI" \
        "export" \
        --standalone \
        --dst-dir "$STAND_ALONE_EXPORT_DIR"
}

@test "export.stop" {
    cd "$FIXTURES"

    "$LAGOCLI" shell "$VM_NAME" "cd /sbin && ./poweroff"
    sleep 3
    common.is_initialized "$WORKDIR" || skip "workdir not initiated"
    helpers.run_ok "$LAGOCLI" stop
}

@test "export.export_stand_alone: stand alone images export" {
    cd "$FIXTURES"

    helpers.run_ok common.is_stopped $WORKDIR
    helpers.run_ok "$LAGOCLI" \
        "export" \
        --standalone \
        --dst-dir "$STAND_ALONE_EXPORT_DIR"
}

@test "export.export_layered: layered images export" {
    cd "$FIXTURES"

    helpers.run_ok common.is_stopped $WORKDIR
    helpers.run_ok "$LAGOCLI" \
        "export" \
        --dst-dir "$LAYERED_EXPORT_DIR"
}

@test "export.remove_base_env" {
    cd "$FIXTURES"

    helpers.run_ok "$LAGOCLI" destroy --yes
}

@test "export.init_exported_sa_env" {
    cd "$STAND_ALONE_EXPORT_DIR"

    local suite="${FIXTURES}/exported_suite.json"
    # will be used by exported_suite.json
    export EXPORTED_ENV=$STAND_ALONE_EXPORT_DIR

    helpers.run_ok "$LAGOCLI" \
        init \
        --template-repo-path "$REPO_CONF" \
        --template-repo-name "$REPO_NAME" \
        --template-store "$STORE" \
        "$suite"
}

@test "export.test_sa_exported_env: testing standalone exported env" {
    cd $FIXTURES
    local dummy_file_content=$(cat dummy_file)
    cd "$STAND_ALONE_EXPORT_DIR"

    helpers.run_ok "$LAGOCLI" start
    dummy_file_inside_content=$("$LAGOCLI" shell "$VM_NAME" "cat /root/dummy_file_inside" | tail -n1)
    helpers.contains "$dummy_file_inside_content" "$dummy_file_content"
}

@test "export.destroy_sa_exported_env: destroying standalone exported env" {
    cd "$STAND_ALONE_EXPORT_DIR"
    helpers.run_ok "$LAGOCLI" destroy --yes
}

@test "export.init_exported_layered_env" {
    cd "$LAYERED_EXPORT_DIR"

    local suite="${FIXTURES}/exported_suite.json"
    # will be used by exported_suite.json
    export EXPORTED_ENV=$LAYERED_EXPORT_DIR

    helpers.run_ok "$LAGOCLI" \
        init \
        --template-repo-path "$REPO_CONF" \
        --template-repo-name "$REPO_NAME" \
        --template-store "$STORE" \
        "$suite"
}

@test "export.test_exported_layered_env: testing layered exported env" {
    cd $FIXTURES
    local dummy_file_content=$(cat dummy_file)
    cd "$LAYERED_EXPORT_DIR"

    helpers.run_ok "$LAGOCLI" start
    dummy_file_inside_content=$("$LAGOCLI" shell "$VM_NAME" "cat /root/dummy_file_inside")
    helpers.contains "$dummy_file_inside_content" "$dummy_file_content"
}

@test "export.destroy_layered_exported_env: destroying layered exported env" {
    cd "$LAYERED_EXPORT_DIR"
    helpers.run_ok "$LAGOCLI" destroy --yes
}
