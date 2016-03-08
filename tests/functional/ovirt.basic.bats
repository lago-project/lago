#!/usr/bin/env bats
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
load common
load ovirt_common
load helpers


@test "ovirt.basic: command shows help" {
    helpers.run_ok \
        "${OVIRTCLI[@]}" -h
    helpers.contains "$output" 'usage:'
}


@test "ovirt.basic: command fails and shows help on wrong option" {
    helpers.run_nook \
        "${OVIRTCLI[@]}" -wrongoption
    helpers.contains "$output" 'usage:'
}


@test "ovirt.basic: make sure all the verbs have help" {
    for verb in "${OVIRT_VERBS[@]}"; do
        helpers.run_ok "${OVIRTCLI[@]}" "$verb" -h
        helpers.equals "$status" '0'
        helpers.contains "$output" 'usage:'
    done
}
