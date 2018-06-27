#!/bin/bash -ex
# Run lago commands inside a running container
# This script assumes that lago's workdir is at $workdir

readonly container="${LAGO_CONTAINER:-lago-container}"
readonly workdir="${LAGO_WORKDIR:-/home/lago-user}"
readonly lago_container_label="com.github.lago-project.lago"

lago_cmd() {
    docker exec -it "$container" lago --workdir "$workdir" "$@"
}

ls_envs() {
    docker ps -a --filter "label=$lago_container_label"
}

current_env() {
    echo "Current env container: $container"
    echo "Current env workdir: $workdir"
}

main() {
    case "$1" in
        ls)
            shift
            ls_envs
            ;;
        *)
            lago_cmd "$@"
    esac
}

[[ "${BASH_SOURCE[0]}" == "$0" ]] && main "$@"

