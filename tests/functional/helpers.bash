#!/usr/bin/env bash

load common

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


helpers.links_to() {
    local what="${1:?}"
    local where="${2:?}"
    helpers.is_link "$what" || return $?
    echo "link $what points to $where"
    [[ "$(readlink "$what")" == "$where" ]]
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
    echo "\"$what\" != \"$to_what\""
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
    base_file="$BATS_TMPDIR/stdout"
    echo "DIFF OUTPUT: Checking if \$output matches $expected_file"
    echo "$output" > "$base_file"
    helpers.diff "$expected_file" "$base_file"
    return $?
}


helpers.diff() {
    local expected_file="${1?}"
    local expected_replaced_file="$expected_file.tmp"
    local base_file="${2?}"
    echo "DIFF:Checking if the $base_file differs from the expected"
    echo "CURRENT(<): $base_file | EXPECTED(>): $expected_file"
    common.realize_lago_template "$expected_file" "$expected_replaced_file"
    diff \
        --ignore-trailing-space \
        "$base_file" \
        "$expected_replaced_file"
    return $?
}


helpers.diff_output_nowarning() {
    local expected_file="${1?}"
    echo "$output" > "$prefix/current"
    echo "DIFF:Checking \$output (unfiltered) matches $expected_file"
    helpers.diff "$expected_file" "$prefix/current"
    return $?
}
