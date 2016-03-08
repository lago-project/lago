#!/bin/bash
#
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
LAGOCLI=lago
VERBS=(
    cleanup
    copy-from-vm
    copy-to-vm
    destroy
    init
    ovirt
    shell
    snapshot
    start
    status
    stop
    template-repo
    console
)
FIXTURES="$BATS_TEST_DIRNAME/fixtures"


common.is_initialized() {
    local prefix="${1?}"
    [[ -e "$prefix/initialized" ]]
    return $?
}


common.initialize() {
    local prefix="${1?}"
    [[ -e "$prefix/initialized" ]] \
    || touch "$prefix/initialized"
}
