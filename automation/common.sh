#!/bin/bash -e
#
# Common functions for the scripts
#

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


build_docs() {
    local docs_dir="${1?}"
    local res=0
    rm -rf "$docs_dir"
    rm -rf tests/docs_venv
    virtualenv -q tests/docs_venv
    source tests/docs_venv/bin/activate
    pip --quiet install --requirement docs/requires.txt
    make docs || res=$?
    deactivate
    mv docs/_build "$docs_dir"
    return $res
}


run_unit_tests() {
    local res=0
    # Style and unit tests, using venv to make sure the installation tests
    # pull in all the dependencies
    rm -rf tests/venv
    # the system packages are needed for python-libguestfs
    virtualenv -q --system-site-packages tests/venv
    source tests/venv/bin/activate
    pip --quiet install --requirement test-requires.txt
    export PYTHONPATH
    make check-local || res=$?
    deactivate
    return $res
}


run_installation_tests() {
    local yum
    local package
    local res=0
    automation/build-artifacts.sh \
    || return $?
    echo "Installing..."
    if hash dnf &>/dev/null; then
        yum=dnf
    else
        yum=yum
    fi
    # fail if a glob turns out empty
    shopt -s failglob
    for package in {python-,}lago {python-,}lago-ovirt; do
        echo "    $package: installing"
        ## Install one by one to make sure the deps are ok
        $yum install -y exported-artifacts/"$package"-[[:digit:]]*.noarch.rpm \
        && echo "    $package: OK" \
        || {
            echo "    $package: FAILED"
            return 1
        }
        if [[ "$package" == "lago" ]]; then
            echo "    Checking that lago imports are not missing"
            lago -h > /dev/null \
            && echo "    OK" \
            || {
                echo "    FAILED"
                return 1
            }

        elif [[ "$package" == "lago-ovirt" ]]; then
            echo "    Checking that lago ovirt imports are not missing"
            lago ovirt -h > /dev/null \
            && echo "    OK" \
            || {
                echo "    FAILED"
                return 1
            }
        fi
    done
    return $res
}


run_basic_functional_tests() {
    local res
    # Ugly fix to be able to run el* on fc*
    if ! [[ -e /usr/bin/qemu-kvm ]]; then
        ln -s /usr/libexec/qemu-kvm /usr/bin/qemu-kvm
    fi
    bats tests/functional/*basic.bats \
    | tee exported-artifacts/functional_tests.tap
    res=${PIPESTATUS[0]}
    return $res
}


run_full_functional_tests() {
    local res
    # Ugly fix to be able to run el* on fc*
    if ! [[ -e /usr/bin/qemu-kvm ]]; then
        ln -s /usr/libexec/qemu-kvm /usr/bin/qemu-kvm
    fi
    bats tests/functional/*.bats \
    | tee exported-artifacts/functional_tests.tap
    res=${PIPESTATUS[0]}
    return $res
}



generate_html_report() {
    cat  >exported-artifacts/index.html <<EOR
    <html>
    <body>
        <ul>
            <li>
                <a href="docs/html/index.html">Docs page</a>
            </li>
EOR
    if code_changed; then
        cat  >>exported-artifacts/index.html <<EOR
            <li>
                <a href="functional_tests.tap">TAP tests result</a>
            </li>
EOR
    fi

    cat  >>exported-artifacts/index.html <<EOR
        </ul>
    </body>
    </html>
EOR
    echo "~ Report at file://$PWD/exported-artifacts/index.html  ~"
}

