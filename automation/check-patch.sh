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


[[ -d "$EXPORTED_DIR" ]] || mkdir -p "$EXPORTED_DIR"

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Building docs                              ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
rm -rf "$DOCS_DIR"
pip install -r docs/requires.txt
make docs
mv docs/_build "$DOCS_DIR"

if ! code_changed; then
    echo " No code changes, skipping code tests"
    exit 0
fi

# Style and unit tests
# required for the formatting
pip install yapf
make check-local

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Running build/installation tests           ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
automation/build-artifacts.sh
# to allow negated groups in globs
shopt -s extglob
# fail if a glob turns out empty
shopt -s failglob
echo "Installing..."
if hash dnf &>/dev/null; then
    dnf install -y exported-artifacts/!(*.src).rpm
else
    yum install -y exported-artifacts/!(*.src).rpm
fi
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
