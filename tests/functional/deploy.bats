#!/usr/bin/env bats
load common
load helpers
load env_setup

FIXTURES="$FIXTURES/deploy"
WORKDIR="$FIXTURES/.lago"
REPO_STORE="$FIXTURES"/repo_store
STORE="$FIXTURES"/store
REPO_CONF="$FIXTURES"/template_repo.json
REPO_NAME='local_tests_repo'

@test "deploy.basic: setup" {
    local suite="$FIXTURES"/suite_1host.yaml

    rm -rf "$WORKDIR"
    pushd "$FIXTURES"
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    export BATS_TMPDIR BATS_TEST_DIRNAME
    rm -rf "$REPO_STORE" "$WORKDIR"
    cp -a "$FIXTURES/store_skel" "$REPO_STORE"
    env_setup.populate_disks "$REPO_STORE"
    local workdir="$FIXTURES"/workdir
    helpers.run_ok "$LAGOCLI" \
        init \
        --template-repo-path "$REPO_CONF" \
        --template-repo-name "$REPO_NAME" \
        --template-store "$STORE" \
        "$WORKDIR" \
        "$suite"
    helpers.is_dir "$WORKDIR/default"
    helpers.links_to "$WORKDIR/current" "default"
    helpers.run_ok "$LAGOCLI" start
}


@test "deploy.basic: deploy" {
    common.is_initialized "$WORKDIR" || skip "Workdir not initiated"
    pushd "$FIXTURES"

    helpers.run_ok "$LAGOCLI" deploy

echo "Checking that the nicefile was properly created"
    helpers.run_ok "$LAGOCLI" shell 'lago_functional_tests_vm01' <<EOC
    cat /root/nicefile
EOC
    helpers.diff_output "$FIXTURES/nicefile"

    echo "Checking that the uglyfile was properly created"
    helpers.run_ok "$LAGOCLI" shell 'lago_functional_tests_vm01' <<EOC
    cat /root/uglyfile
EOC
    helpers.diff_output "$FIXTURES/uglyfile"
}


@test "deploy.basic: teardown" {
    if common.is_initialized "$WORKDIR"; then
        pushd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" destroy -y
        popd
    fi
    env_setup.destroy_domains
    env_setup.destroy_nets
}


@test "deploy.fail_on_deploy_failure: setup" {
    # As there's no way to know the last test result, we will handle it here
    local suite="$FIXTURES"/suite_1host_fail.yaml

    pushd "$FIXTURES"
    rm -rf "$WORKDIR"
    export BATS_TMPDIR BATS_TEST_DIRNAME
    helpers.run_ok "$LAGOCLI" \
        init \
        --template-repo-path "$REPO_CONF" \
        --template-repo-name "$REPO_NAME" \
        --template-store "$STORE" \
        "$WORKDIR" \
        "$suite"
    helpers.is_dir "$WORKDIR/default"
    helpers.links_to "$WORKDIR/current" "default"
    helpers.run_ok "$LAGOCLI" start
}


@test "deploy.fail_on_deploy_failure: failed deploy" {
    common.is_initialized "$WORKDIR" || skip "Workdir not initiated"
    pushd "$FIXTURES"

    helpers.run_nook "$LAGOCLI" --loglevel debug deploy
    helpers.contains "$output" "I'm going to fail"
}


@test "deploy.fail_on_deploy_failure: teardown" {
    if common.is_initialized "$WORKDIR"; then
        pushd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" destroy -y
        popd
    fi
    env_setup.destroy_domains
    env_setup.destroy_nets
}
