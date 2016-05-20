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

git diff \
    HEAD^ \
    --name-status \
| grep -v "^D" \
| grep "\.py$" \
| awk '{ print $2 }' \
| xargs yapf \
    --style .style.yapf \
    --diff \
|| {
    cat <<EOF
Yapf failed, make sure to run:
    yapf --style .style.yapf --in-place --recursive .

to format any python files automatically, it is higly recommended that you
install formatting tools to your editor, check the yapf repo:

     https://github.com/google/yapf/tree/master/plugins

to check for official support (always helpful).
You can also install the pre-commit hook provided in this repo:

    ln -s scripts/pre-commit.style .git/pre-commit

and it will format any files changed at commit time.

EOF
    exit 1
}

exit 0
