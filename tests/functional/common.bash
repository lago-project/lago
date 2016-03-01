#!/bin/bash
LAGOCLI=lago
VERBS=(
    cleanup
    copy-from-vm
    copy-to-vm
    destroy
    init
    ovirt
    shell
    snapshot
    start
    status
    stop
    template-repo
    console
)
FIXTURES="$BATS_TEST_DIRNAME/fixtures"


common.is_initialized() {
    local prefix="${1?}"
    [[ -e "$prefix/initialized" ]]
    return $?
}


common.initialize() {
    local prefix="${1?}"
    [[ -e "$prefix/initialized" ]] \
    || touch "$prefix/initialized"
}
