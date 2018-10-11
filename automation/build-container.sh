#!/bin/bash -ex

${0%/*}/build-artifacts.sh
make container RPM_PATH="$(realpath exported-artifacts)"
