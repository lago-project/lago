#!/bin/bash -e
EXPORTED_DIR="$PWD/exported-artifacts"
DOCS_DIR="$EXPORTED_DIR/docs"


[[ -d "$EXPORTED_DIR" ]] || mkdir -p "$EXPORTED_DIR"

echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~*          Building docs                              ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
rm -rf "$DOCS_DIR"
pip install -r docs/requires.txt
make docs
mv docs/_build "$DOCS_DIR"

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
echo '~*          Running functional tests                   ~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
# Ugly fix to be able to run el* on fc*
if ! [[ -e /usr/bin/qemu-kvm ]]; then
    ln -s /usr/libexec/qemu-kvm /usr/bin/qemu-kvm
fi
bats tests/functional \
| tee exported-artifacts/functional_tests.tap
res=${PIPESTATUS[0]}
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
echo '~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~'
exit "$res"
