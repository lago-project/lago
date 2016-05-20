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
"""
Utilities to help deal with the libvirt python bindings
"""
import libvirt

#: Mapping of domain statuses values to human readable strings
DOMAIN_STATES = {
    libvirt.VIR_DOMAIN_NOSTATE: 'no state',
    libvirt.VIR_DOMAIN_RUNNING: 'running',
    libvirt.VIR_DOMAIN_BLOCKED: 'blocked',
    libvirt.VIR_DOMAIN_PAUSED: 'paused',
    libvirt.VIR_DOMAIN_SHUTDOWN: 'beign shut down',
    libvirt.VIR_DOMAIN_SHUTOFF: 'shut off',
    libvirt.VIR_DOMAIN_CRASHED: 'crashed',
    libvirt.VIR_DOMAIN_PMSUSPENDED: 'suspended',
}

#: Singleton with the cached opened libvirt connections
LIBVIRT_CONNECTIONS = {}


class Domain(object):
    """
    Class to namespace libvirt domain related helpers
    """

    @staticmethod
    def resolve_state(state_number):
        """
        Get a nice description from a domain state number

        Args:
            state_number(list of int): State number as returned by
                :func:`libvirt.virDomain.state`

        Returns:
            str: small human readable description of the domain state, unknown
                if the state is not in the known list
        """
        return DOMAIN_STATES.get(state_number[0], 'unknown')


def get_libvirt_connection(name, libvirt_url='qemu://system'):
    if name not in LIBVIRT_CONNECTIONS:
        LIBVIRT_CONNECTIONS[name] = libvirt.open(libvirt_url)

    return LIBVIRT_CONNECTIONS[name]
