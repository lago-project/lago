#!/bin/bash -xe
readonly STAGE="$1"
readonly EXPORTED_DIR="$PWD/exported-artifacts"
readonly OUT_DOCS_DIR="$EXPORTED_DIR/docs"
source "${0%/*}/common.sh"

rm -rf "$EXPORTED_DIR"
mkdir -p "$EXPORTED_DIR"

res=0

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Building docs                              ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
setup_tox
build_docs || res=$?
fail_nonzero "$res" "Failed building docs, run locally with: tox -e docs"
mv -v docs/_build "$OUT_DOCS_DIR"/


if ! code_changed; then
    echo "No code changes, skipping tests"
    exit 0
fi

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running unit tests                         ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
run_unit_tests || res=$?
collect_test_results "$PWD/" \
    "$EXPORTED_DIR/test_results/unittest"
fail_nonzero "$res" "Failed running unit tests, exiting"

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running build/installation tests           ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
run_installation_tests || res=$?
fail_nonzero "$res" "Failed running installation tests, exiting"

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running functional tests                   ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
set_virt_params
run_functional_tests "$STAGE" || res=$?
collect_test_results "$PWD/tests/functional" \
    "$EXPORTED_DIR/test_results/functional-cli"
collect_test_results "$PWD/tests/functional-sdk" \
    "$EXPORTED_DIR/test_results/functional-sdk"
fail_nonzero "$res" "Failed running functional tests, exiting"

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Generating html report                     ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
generate_html_report
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
