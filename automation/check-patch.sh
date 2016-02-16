#!/bin/bash -e
EXPORTED_DIR="$PWD/exported-artifacts"
DOCS_DIR="$EXPORTED_DIR/docs"

code_changed() {
    if ! [[ -d .git ]]; then
        echo "Not in a git dir, will run all the tests"
        return 0
    fi
    git diff-tree --no-commit-id --name-only -r HEAD..HEAD^ \
    | grep --quiet -v -e '\(docs/\|README.md\)'
    return $?
}

die() {
    echo "$@"
    exit 1
}


[[ -d "$EXPORTED_DIR" ]] || mkdir -p "$EXPORTED_DIR"

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Building docs                              ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
rm -rf "$DOCS_DIR"
rm -rf tests/docs_venv
virtualenv -q tests/docs_venv
source tests/docs_venv/bin/activate
pip --quiet install --requirement docs/requires.txt
make docs
deactivate
mv docs/_build "$DOCS_DIR"

if ! code_changed; then
    echo " No code changes, skipping code tests"
    exit 0
fi

# Style and unit tests, using venv to make sure the installation tests pull in
# all the dependencies
rm -rf tests/venv
# the system packages are needed for python-libguestfs
virtualenv -q --system-site-packages tests/venv
source tests/venv/bin/activate
pip --quiet install --requirement test-requires.txt
export PYTHONPATH
make check-local
deactivate

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running build/installation tests           ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
automation/build-artifacts.sh
echo "Installing..."
if hash dnf &>/dev/null; then
    YUM=dnf
else
    YUM=yum
fi
# to allow negated groups in globs
shopt -s extglob
# fail if a glob turns out empty
shopt -s failglob
for package in {python-,}lago {python-,}lago-ovirt; do
    echo "    $package: installing"
    ## Install one by one to make sure the deps are ok
    $YUM install -y exported-artifacts/"$package"-[[:digit:]]!(*src).rpm \
    && echo "    $package: OK" \
    || die "    $package: FAILED"
    if [[ "$package" == "lago" ]]; then
        echo "    Checking that lago imports are not missing"
        lago -h > /dev/null \
        && echo "    OK" \
        || die "    FAILED"

    elif [[ "$package" == "lago-ovirt" ]]; then
        echo "    Checking that lago ovirt imports are not missing"
        lago ovirt -h > /dev/null \
        && echo "    OK" \
        || die "    FAILED"
    fi
done
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running basic functional tests             ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
# Ugly fix to be able to run el* on fc*
if ! [[ -e /usr/bin/qemu-kvm ]]; then
    ln -s /usr/libexec/qemu-kvm /usr/bin/qemu-kvm
fi
bats tests/functional/*basic.bats \
| tee exported-artifacts/basic_functional_tests.tap
res=${PIPESTATUS[0]}
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Generating html report                     ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
cat  >exported-artifacts/index.html <<EOR
<html>
<body>
<ul>
<li>
  <a href="docs/html/index.html">Docs page</a>
</li>
<li>
  <a href="basic_functional_tests.tap">TAP tests result</a>
</li>
</ul
</body>
</html>
EOR
echo "~ Report at file://$PWD/exported-artifacts/index.html  ~"
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
exit "$res"
