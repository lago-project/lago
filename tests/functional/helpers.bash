#!/usr/bin/env bash

helpers.exists() {
    local what="${1:?}"
    echo "exists $what"
    [[ -e "$what" ]]
    return $?
}

helpers.not_exists() {
    local what="${1:?}"
    echo "not exists $what"
    ! [[ -e "$what" ]]
    return $?
}

helpers.is_file() {
    local what="${1:?}"
    echo "is file $what"
    [[ -f "$what" ]]
    return $?
}

helpers.is_dir() {
    local what="${1:?}"
    echo "is dir $what"
    [[ -d "$what" ]]
    return $?
}

helpers.is_link() {
    local what="${1:?}"
    echo "is link $what"
    [[ -L "$what" ]]
    return $?
}

helpers.run() {
    echo "RUNNING:$@"
    run "$@"
    echo "--output--"
    echo "$output"
    echo "---"
    return 0
}


helpers.run_ok() {
    helpers.run "$@"
    helpers.equals "$status" '0'
}


helpers.run_nook() {
    helpers.run "$@"
    helpers.different "$status" '0'
}


helpers.equals() {
    local what="${1:?}"
    local to_what="${2:?}"
    echo "\"$what\" == \"$to_what\""
    [[ "$what" == "$to_what" ]]
    return $?
}


helpers.different() {
    local what="${1:?}"
    local to_what="${2:?}"
    echo "\"$what\" == \"$to_what\""
    [[ "$what" != "$to_what" ]]
    return $?
}

helpers.contains() {
    local continent="${1:?}"
    local contents=("${@:2}")
    local content
    for content in "${contents[@]}"; do
        echo "\"$continent\" =~ $content"
        [[ "$continent" =~ $content ]] \
        || return $?
    done
    return 0
}

helpers.matches() {
    helpers.contains "$@"
    return $?
}


helpers.diff_output() {
    local expected_file="${1?}"
    local expected_replaced_file="$expected_file.tmp"
    echo "$output" \
    | tail -n+2 \
    > "$prefix/current"
    echo "DIFF:Checking if the output differs from the expected"
    echo "CURRENT(<): output | EXPECTED(>): $expected_file"
    sed \
        -e "s|@@PREFIX_PATH@@|$PREFIX_PATH|g" \
        -e "s|@@PREFIX@@|$PREFIX|g" \
        -e "s|@@BATS_TEST_DIRNAME@@|$BATS_TEST_DIRNAME|g" \
        "$expected_file" \
    > "$expected_replaced_file"
    # replace each vnc port appearance
    local vnc_ports=($(grep -Po '(?<=VNC port: )\d+' "$prefix/current")) || :
    local vnc_port
    for vnc_port in "${vnc_ports[@]}"; do
        sed -i \
            -e "0,/@@VNC_PORT@@/{s/@@VNC_PORT@@/${vnc_port:=no port found}/}" \
            "$expected_replaced_file"
    done
    diff \
        "$prefix/current" \
        "$expected_replaced_file"
    return $?
}
