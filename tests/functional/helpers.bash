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
    [[ "$what" == "$to_what" ]]
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
