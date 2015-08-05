#!/bin/sh -xe
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
if [ $# -lt 3 ];
then
	echo "Usage:"
	echo "$0 SOURCE_DIR RESULT_DIR DIST1 ... DISTn"
	echo "This builds VDSM from source provided in SOURCE_DIR"
	echo "RPMs are built inside mock environment for each one of"
	echo "specified distributions (DISTx)."
fi

SOURCE_DIR=$1
RESULT_DIR=$2

shift 2
DISTS=$@

echo "Source directory: ${SOURCE_DIR?}"
echo "Result directory: ${RESULT_DIR?}"
echo "Build for following dists: ${DISTS?}"

cd "${SOURCE_DIR?}"
rm -rf "${PWD?}/rpmbuild"
rm -rf ${PWD?}/*.tar.gz

./autogen.sh --system
make dist
rpmbuild -ts *.tar.gz -D "_topdir ${PWD}/rpmbuild"

SRPM_PATH=$(realpath ${PWD}/rpmbuild/SRPMS/*.src.rpm)

export NOSE_EXCLUDE='.*'

for DIST in ${DISTS?};
do
	case "${DIST?}" in
		el6)
			MOCK_CFG="epel-6-x86_64"
			;;
		el7)
			MOCK_CFG="epel-7-x86_64"
			;;
		fc21)
			MOCK_CFG="fedora-21-x86_64"
			;;
		fc22)
			MOCK_CFG="fedora-22-x86_64"
			;;
	esac
	rm -rf "${RESULT_DIR?}/${DIST?}"
	mkdir -p "${RESULT_DIR?}/${DIST?}"
	/usr/bin/mock \
		--root="${MOCK_CFG?}" \
		--resultdir="${RESULT_DIR?}/${DIST?}" \
		--rebuild \
		"${SRPM_PATH?}" \
		&
done

for PID in $(jobs -p);
do
	wait ${PID?} || exit 1
done
