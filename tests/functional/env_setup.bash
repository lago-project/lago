#!/bin/bash
DEFAULT_BASE_IMAGE="$BATS_TEST_DIRNAME/fixtures/minimal_vm.qcow2.gz"


env_setup.populate_disks() {
    local prefix="${1?}"
    local base_image="${2:-$DEFAULT_BASE_IMAGE}"
    local skel_image

    shopt -s nullglob
    echo "Decompressing $base_image"
    gunzip -c "$base_image" > "$prefix"/base_image
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
