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
DEFAULT_BASE_IMAGE="$BATS_TEST_DIRNAME/fixtures/minimal_vm.qcow2.gz"


env_setup.populate_disks() {
    local prefix="${1?}"
    local base_image="${2:-$DEFAULT_BASE_IMAGE}"
    local skel_image

    shopt -s nullglob
    echo "Decompressing $base_image"
    xzcat "$base_image" > "$prefix"/base_image
    for skel_image in "$prefix"/images/*.skel "$prefix"/*skel; do
        cp "$prefix"/base_image "${skel_image%.skel}"
        echo "Realized skel disk $skel_image to ${skel_image%.skel}"
    done
    rm -f "$prefix"/base_image
    return 0
}


env_setup.destroy_domains() {
    local vm_prefix="${1:-lago_functional_tests}"
    for domain in $(virsh list --name --all); do
        if [[ "$domain" =~ $vm_prefix ]]; then
            virsh destroy "$domain"
        fi
    done
}

env_setup.destroy_nets() {
    local vm_prefix="${1:-lago_functional_tests}"
    for net in $(virsh net-list --all | awk '{ print $1; }'); do
        net="${net}"
        if [[ "$net" =~ $vm_prefix ]]; then
            virsh net-destroy "$net"
        fi
    done
}
