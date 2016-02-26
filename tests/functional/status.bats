#!/usr/bin/env bats
LAGOCLI=lagocli
FIXTURES="$BATS_TEST_DIRNAME/fixtures/status"
PREFIX="$FIXTURES/prefix"


load helpers
load env_setup


@test "status: setup" {
    rm -rf "$PREFIX"
    cp -a "$FIXTURES"/prefix_skel "$PREFIX"
    env_setup.populate_disks "$PREFIX"
}


@test "status: simple status run on stopped prefix" {
    pushd "$PREFIX" >/dev/null
    helpers.run "$LAGOCLI" status
    helpers.equals "$status" '0'

    echo "DIFF:Checking if the output differs from the expected"
    expected_file="$PREFIX/expected"
    current_file="$PREFIX/current"
    echo "$output" \
    | tail -n+2 \
    > "$current_file"
    sed \
        -i \
        -e "s|@@PREFIX@@|$PREFIX|g" \
        "$expected_file"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "$current_file" \
        "$expected_file"
}


@test "status: json status run on stopped prefix" {
    pushd "$PREFIX" >/dev/null
    helpers.run "$LAGOCLI" --out-format json status
    helpers.equals "$status" '0'

    echo "DIFF:Checking if the output differs from the expected"
    expected_file="$PREFIX/expected.json"
    current_file="$PREFIX/current"
    echo "$output" \
    | tail -n+2 \
    > "$current_file"
    sed \
        -i \
        -e "s|@@PREFIX@@|$PREFIX|g" \
        "$expected_file"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "$current_file" \
        "$expected_file"
}

@test "status: yaml status run on stopped prefix" {
    pushd "$PREFIX" >/dev/null
    helpers.run "$LAGOCLI" -f yaml status
    helpers.equals "$status" '0'

    echo "DIFF:Checking if the output differs from the expected"
    expected_file="$PREFIX/expected.yaml"
    current_file="$PREFIX/current"
    echo "$output" \
    | tail -n+2 \
    > "$current_file"
    sed \
        -i \
        -e "s|@@PREFIX@@|$PREFIX|g" \
        "$expected_file"
    diff \
        --suppress-common-lines \
        --side-by-side \
        "$current_file" \
        "$expected_file"
}
