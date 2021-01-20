#!/bin/bash -ex
#
# Common functions for the scripts
#

readonly PIP_CACHE_DIR=/var/tmp/lago_pip_cache

readonly CHECK_PATCH_BATS=('basic.bats' \
    'collect.bats' \
    'deploy.bats' \
    'start.bats' \
    'status.bats' )

readonly CHECK_MERGED_BATS=('snapshot.bats')

fail_nonzero() {
    local res msg
    res=$1
    msg=$2
    if [[ "$res" -ne 0 ]]; then
        echo "$msg"
        exit "$res"
    fi
}


set_virt_params() {
    # see: https://bugzilla.redhat.com/show_bug.cgi?id=1404287
    export LIBGUESTFS_APPEND="edd=off"
    # make libguestfs use /dev/shm as tmpdir
    export LIBGUESTFS_CACHEDIR="/dev/shm"
    export LIBGUESTFS_TMPDIR="/dev/shm"

    # ensure KVM is enabled under mock
    ! [[ -c "/dev/kvm" ]] && mknod /dev/kvm c 10 232

    export LIBGUESTFS_DEBUG=1 LIBGUESTFS_TRACE=1

    export LIBVIRT_LOG_OUTPUTS="1:file:$PWD/exported-artifacts/libvirtd.log"

    [[ -e /etc/sudoers ]] \
    && sed -i -e 's/^Defaults\s*requiretty/Defaults !requiretty/' /etc/sudoers
}

code_changed() {
    if ! [[ -d .git ]]; then
        echo "Not in a git dir, will run all the tests"
        return 0
    fi
    git diff-tree --no-commit-id --name-only -r HEAD..HEAD^ \
    | grep --quiet -v -e '\(docs/\|README.rst\)'
    return $?
}

die() {
    echo "$@"
    exit 1
}

setup_tox() {
    # to-do: add support for pip cache in standard-ci
    export PATH="$PATH:/usr/local/bin"
    mkdir -p "$PIP_CACHE_DIR"
    chown -R "$USER:" "$PIP_CACHE_DIR"
    export PIP_CACHE_DIR
    # https://github.com/pypa/setuptools/issues/1042
    for package in "tox" "virtualenv<20"; do
        python3 -m pip install --upgrade "$package" || return 1
    done
}

build_docs() {
    make docs
}


run_unit_tests() {
    make check-local
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
    echo "Running sdist installation tests"
    tox -v -r -e sdist

    # fail if a glob turns out empty
    shopt -s failglob
    for package in {python3-,}lago ; do
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
        fi
    done
    return $res
}


run_functional_cli_tests() {
    local res=0
    local tests
    tests=("$@")
    pushd tests/functional
    bats "${tests[@]}" | tee functional_tests.tap
    res=${PIPESTATUS[0]}
    popd
    return "$res"
}

run_functional_sdk_tests() {
    local stage
    stage="$1"

    unset LAGO__START__WAIT_SUSPEND
    TEST_RESULTS="$PWD/exported-artifacts/test_results/functional-sdk" \
       tox -v -r -c tox-sdk.ini -e py3-sdk -- --stage "$stage"
}

run_functional_tests() {
    local stage tests_var
    stage="$1"
    tests_var="${stage^^}_BATS[@]"
    run_functional_cli_tests "${!tests_var}" || return $?
    run_functional_sdk_tests "$stage"
}



collect_test_results() {
    local dest from
    from="$1"
    dest="$2"
    mkdir -p "$dest"
    find "$from/" \
        \( -iname "*.junit.xml" \
        -o \
        -iname "coverage.xml" \
        -o \
        \( -type d -iname "htmlcov" \) \
        -o \
        -iname "flake8.txt" \
        -o \
        -iname "*.tap" \
        \) \
        -and ! -iname "*$dest*" \
        -print \
        -exec mv -v -t "$dest"  {} \+
}

generate_html_report() {
    cat  >exported-artifacts/index.html <<EOR
    <html>
    <body>
            <li>
                <a href="docs/html/index.html">Docs page</a>
            </li>
EOR
    if code_changed; then

        cat  >>exported-artifacts/index.html <<EOR
            <li>
                <a href="test_results/unittest/htmlcov/index.html">\
                    Unittest coverage.py report</a>
            </li>
            <li>
                <a href="test_results/functional-cli/functional_tests.tap">\
                    Functional CLI tests result</a>
            </li>
            <li>
                <a href="test_results/functional-sdk/htmlcov/index.html">\
                    Functional SDK tests coverage.py report</a>
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
