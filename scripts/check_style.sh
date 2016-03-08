#!/bin/bash -e
# Copyright 2014 Red Hat, Inc.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301 USA
#
# Refer to the README and COPYING files for full details of the license
#

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
