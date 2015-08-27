#!/usr/bin/env bats
OVIRTCLI=(
    lagocli
    ovirt
)
VERBS=(
    collect
    deploy
    engine-setup
    reposetup
    revert
    runtest
    serve
    snapshot
    start
    stop
)

load helpers

@test "ovirt.basic: command shows help" {
    helpers.run \
        "${OVIRTCLI[@]}" -h
    helpers.equals "$status" '0'
    helpers.contains "$output" 'usage:'
}


@test "ovirt.basic: command fails and shows help on wrong option" {
    helpers.run \
        "${OVIRTCLI[@]}" -wrongoption
    ! helpers.equals "$status" '0'
    helpers.contains "$output" 'usage:'
}


@test "ovirt.basic: make sure all the verbs have help" {
    for verb in "${VERBS[@]}"; do
        helpers.run "${OVIRTCLI[@]}" "$verb" -h
        # shell is a special case so far, and needs it's own treatment
        # will be generalized with https://gerrit.ovirt.org/#/c/45314/
        if [[ "$verb" == 'shell' ]]; then
            helpers.equals "$status" '1'
            helpers.contains "$output" 'usage:'
        else
            helpers.equals "$status" '0'
            helpers.contains "$output" 'usage:'
        fi
    done
}
