#!/bin/bash -xe
readonly EXPORTED_DIR="$PWD/exported-artifacts"
readonly OUT_DOCS_DIR="$EXPORTED_DIR/docs"


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
if code_changed; then
    run_unit_tests \
    || res=$?
    collect_test_results "$PWD/" \
        "$EXPORTED_DIR/test_results/unittest"
else
    echo " No code changes, skipping static/unit tests"
fi

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running build/installation tests           ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'

if code_changed && [[ "$res" == "0" ]]; then
    run_installation_tests \
    || res=$?
elif [[ "$res" == "0" ]]; then
    echo " No code changes, skipping installation tests"
else
    echo " Already failed, skipping"
fi

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running basic functional tests             ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'

if code_changed && [[ "$res" == "0" ]]; then
    set_virt_params
    run_functional_tests "check_patch" \
    || res=$?

    collect_test_results "$PWD/tests/functional" \
        "$EXPORTED_DIR/test_results/functional-cli"
    collect_test_results "$PWD/tests/functional-sdk" \
        "$EXPORTED_DIR/test_results/functional-sdk"

elif [[ "$res" == "0" ]]; then
    echo " No code changes, skipping basic functional tests"
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
