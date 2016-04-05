#!/usr/bin/env bats
load common
load helpers
load env_setup

FIXTURES="$FIXTURES/deploy"
PREFIX="$FIXTURES"/.lago


@test "deploy.basic: setup" {
    local suite="$FIXTURES"/suite_1host.yaml

    rm -rf "$PREFIX"
    pushd "$FIXTURES"
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    helpers.run_ok "$LAGOCLI" \
        init \
        "$suite"
    helpers.run_ok "$LAGOCLI" start
}


@test "deploy.basic: deploy" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
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
    if common.is_initialized "$PREFIX"; then
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

    rm -rf "$PREFIX"
    pushd "$FIXTURES"
    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1
    helpers.run_ok "$LAGOCLI" \
        init \
        "$suite"
    helpers.run_ok "$LAGOCLI" start
}


@test "deploy.fail_on_deploy_failure: failed deploy" {
    common.is_initialized "$PREFIX" || skip "prefix not initiated"
    pushd "$FIXTURES"

    helpers.run_nook "$LAGOCLI" --loglevel debug deploy
    helpers.contains "$output" "I'm going to fail"
}


@test "deploy.fail_on_deploy_failure: teardown" {
    if common.is_initialized "$PREFIX"; then
        pushd "$FIXTURES"
        helpers.run_ok "$LAGOCLI" destroy -y
        popd
    fi
    env_setup.destroy_domains
    env_setup.destroy_nets
}
