#!/bin/bash -ex
set -o pipefail
shopt -s failglob

get_rpms() {
    local rpm_path="${1:?}"
    local rpms=()

    for pkg in {python-,}lago; do
        rpms+=($(realpath "${rpm_path}/${pkg}*.noarch.rpm"))
    done

    echo "${rpms[@]}"
}

get_lago_version() {
    local rpm_path="${1:?}"
    local pkg

    pkg="$(get_rpms "$rpm_path" | awk '{ print $1 }' )"
    [[ "$pkg" ]] || {
        echo "Error: Failed to find lago* package in $rpm_path"
        exit 1
    }

    rpm -qp "$pkg" --queryformat '%{version}'
}

render_dockerfile() {
    local libvirt_container="${1:?}"
    local build_context="${2:?}"

    sed "s/@BASE@/${libvirt_container}/g" \
		< "${build_context}/Dockerfile.in" \
		> "${build_context}/Dockerfile"
}

main() {
    local rpm_path="${1:?Error: RPM path must be provided}"
    local libvirt_container="${2:?Error: Base libvirt container must be provided}"
    local build_context="${3:?Error: Build context must be provided}"
    local lago_version name

    lago_version="$(get_lago_version "$rpm_path")"
    tag="lago:${lago_version}"

    render_dockerfile "$libvirt_container" "$build_context"

    cp $(get_rpms "$rpm_path") "$build_context"

    (
        cd "$build_context"
	    docker build \
		    -t "${tag}" \
		    --build-arg lago_version="$lago_version" \
		    .
    )
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"

