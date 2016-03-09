#!/bin/bash
BASE_DIR="${1}"
packages=("${@:2}")

for package in "${packages[@]}"; do
    echo "  Pulling $package"
    for libs_dir in $BASE_DIR/lib/python*; do
        for i in $(rpm -ql "$package"); do
            [[ "$i" =~ ^.*site-packages.*$ ]] || continue
            dst="$libs_dir/site-packages${i##*site-packages}"
            mkdir -p "${dst%/*}"
            echo "      Installing $i -> $dst"
            cp -a "$i" "$dst"
        done
    done
done
