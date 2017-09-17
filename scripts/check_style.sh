#!/bin/bash -e

[[ "$1" == "-v" ]] && shift && set -x

files="$( \
    git diff \
        HEAD^ \
        --name-status \
    | grep -v "^D" \
    | grep "\.py$" \
    | awk '{ print $2 }' \
)"

if [[ "$files" == "" ]]; then
    exit 0
fi

yapf --version
echo "running yapf on the following files:"
echo "$files"

echo "yapf diff:"
if yapf --style .style.yapf --diff --parallel $files; then
    echo "no diff"
    echo "yapf style check: OK"
else
    cat <<EOF
    ***************************************************************************
    Yapf failed, make sure to run:
        yapf --style .style.yapf --in-place --recursive .

    If you want to make it run faster, on python2 ensure you have 'futures'
    installed from pip and run:
        yapf --style .style.yapf --in-place --parallel --recursive .

    To format any python files automatically, it is higly recommended that you
    install formatting tools to your editor, check the yapf repo:

        https://github.com/google/yapf/tree/master/plugins

    To check for official support (always helpful).
    You can also install the pre-commit hook provided in this repo:

        ln -s scripts/pre-commit.style .git/pre-commit

    and it will format any files changed at commit time.
    ***************************************************************************
EOF
    exit 1
fi
