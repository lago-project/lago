#!/bin/bash
LAGOCLI=lago
VERBS=(
    cleanup
    collect
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
    local workdir="${1?}"
    local initfile
    shopt -s nullglob
    for initfile in "$workdir/initialized" "$workdir"/*/initialized; do
        if [[ -e "$initfile" ]]; then
            return 0
        fi
    done
    return 1
}


common.initialize() {
    local prefix="${1?}"
    [[ -e "$prefix/initialized" ]] \
    || touch "$prefix/initialized"
}



common.realize_lago_template() {
    local template_file="${1?}"
    local dst_file="${2:-$template_file.tmp}"
    if [[ -z "$UUID" ]]; then
        if [[ -e "$PREFIX" ]]; then
            local UUID="${UUID:-$(cat "$PREFIX/uuid")}"
        elif [[ -e "$WORKDIR" ]]; then
            local UUID="${UUID:-$(cat "$WORKDIR/${PREFIX_NAME:-current}/uuid")}"
        fi
    fi
    if [[ -z "$PREFIX_NAME" ]]; then
        local PREFIX_NAME="default"
    fi
    if [[ -z "$PREFIX_PATH" ]]; then
        if [[ -n "$PREFIX" ]]; then
            local PREFIX_PATH="$PREFIX"
        elif [[ -n "$WORKDIR" ]] && [[ -n "$PREFIX_NAME" ]]; then
            local PREFIX_PATH="$WORKDIR/$PREFIX_NAME"
            local PREFIX="$WORKDIR/$PREFIX_NAME"
        fi
    fi
    common.realize_template "$template_file" "$dst_file"
    if [[ -e "$BATS_TMPDIR/stdout" ]]; then
        # replace each vnc port for each vm
        local vnc_ports=($(\
            grep -Po '(?<=VNC port: )\d+' "$BATS_TMPDIR/stdout"\
        )) || :
        local vnc_port
        for vnc_port in "${vnc_ports[@]}"; do
            sed -i \
                -e "0,/@@VNC_PORT@@/{s/@@VNC_PORT@@/${vnc_port:=no port found}/}" \
                "$dst_file"
        done
        # Replace the ips
        local ips=($(\
            grep -Po '(?<=ip: )\d+\.\d+\.\d+\.\d+' "$BATS_TMPDIR/stdout"\
        )) || :
        local ip
        for ip in "${ips[@]}"; do
            sed -i \
                -e "0,/@@IP@@/{s/@@IP@@/${ip:=no ip found}/}" \
                "$dst_file"
        done
        # replace the gateway too
        local gateways=($(\
            grep -Po '(?<=gateway: )\d+\.\d+\.\d+\.\d+' "$BATS_TMPDIR/stdout"\
        )) || :
        local gateway
        for gateway in "${gateways[@]}"; do
            sed -i \
                -e "0,/@@GATEWAY@@/{s/@@GATEWAY@@/${gateway:=no gateway found}/}" \
                "$dst_file"
        done
    fi
}


common.realize_template() {
    local template_file="${1?}"
    local dst_file="${2:-$template_file.tmp}"
    local vars=($(\
        set \
        | grep -Po "^\w+(?==)" \
        | grep -Pv "(IFS|LS_COLORS|output|lines)" \
    ))
    local sedlines=()
    local value
    echo "Replacing into $expected_file:"
    for var in "${vars[@]}"; do
        value="${!var}"
        value="${value//[\|\'\\]/_}"
        echo "@@$var@@ -> ${!var}"
        sedlines+=("-e" "s|@@$var@@|$value|g")
    done
    sed "${sedlines[@]}" "$template_file" \
    > "$dst_file"
}
