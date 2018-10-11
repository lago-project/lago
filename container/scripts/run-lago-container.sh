#!/bin/bash

readonly lago_data_dir="${1:?}"
readonly image_name="${2:?}"
readonly container_name="$3"

# This method is still WIP
# Currently libvirt complains that /sys is readonly
restricted() {
    docker run \
        -it \
        -v /sys/fs/cgroup:/sys/fs/cgroup:ro \
        -v "${lago_data_dir}":/var/lib/lago \
        --cap-add NET_ADMIN \
        --cap-add SYS_PTRACE \
        --device /dev/kvm \
        --device /dev/net/tun \
        --name "$container_name" \
        "$image_name"
}

privileged() {
    local subnet_dir && subnet_dir="$(mktemp -d)"

    chmod 777 "$subnet_dir"

    docker run \
        -d \
        -v "${lago_data_dir}":/var/lib/lago \
        -v "${subnet_dir}":/var/lib/lago/subnets \
        --privileged \
        --name "$container_name" \
        "$image_name"
}

privileged
