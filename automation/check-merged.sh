#!/bin/bash -e
EXPORTED_DIR="$PWD/exported-artifacts"
OUT_DOCS_DIR="$EXPORTED_DIR/docs"


source "${0%/*}/common.sh"


[[ -d "$EXPORTED_DIR" ]] || mkdir -p "$EXPORTED_DIR"

res=0

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Building docs                              ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'

setup_tox
build_docs && mv -v docs/_build "$OUT_DOCS_DIR"/

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running static/unit tests                  ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
run_unit_tests \
|| res=$?

collect_test_results "$PWD/" \
    "$EXPORTED_DIR/test_results/unittest"
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running build/installation tests           ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
if [[ "$res" == "0" ]]; then
    run_installation_tests \
    || res=$?
else
    echo " Already failed, skipping"
fi

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running functional tests                   ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
if [[ "$res" == "0" ]]; then
    set_virt_params
    run_full_functional_tests \
    || res=$?
    collect_test_results "$PWD/tests/functional" \
        "$EXPORTED_DIR/test_results/functional-cli"
else
    echo " Already failed, skipping"
fi

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Generating html report                     ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
generate_html_report

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
exit "$res"
