#!/usr/bin/env bats
load common
load helpers
load env_setup


FIXTURES="$FIXTURES/status"
PREFIX="$FIXTURES/prefix"


@test "status: setup" {
    rm -rf "$PREFIX"
    cp -a "$FIXTURES"/prefix_skel "$PREFIX"
    env_setup.populate_disks "$PREFIX"
}


@test "status: simple status run on stopped prefix" {
    pushd "$PREFIX" >/dev/null
    helpers.run_ok "$LAGOCLI" status
    helpers.diff_output "$PREFIX/expected"
}


@test "status: json status run on stopped prefix" {
    pushd "$PREFIX" >/dev/null
    helpers.run_ok "$LAGOCLI" --out-format json status
    helpers.diff_output "$PREFIX/expected.json"
}

@test "status: yaml status run on stopped prefix" {
    pushd "$PREFIX" >/dev/null
    helpers.run_ok "$LAGOCLI" -f yaml status
    helpers.diff_output "$PREFIX/expected.yaml"
}
