#
# Copyright 2014-2017 Red Hat, Inc.
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
import pkg_resources
import xmltodict
import lxml.etree
from lago.config import config

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


def auth_callback(credentials, user_data):
    for credential in credentials:
        if credential[0] == libvirt.VIR_CRED_AUTHNAME:
            credential[4] = config.get('libvirt_username')
        elif credential[0] == libvirt.VIR_CRED_PASSPHRASE:
            credential[4] = config.get('libvirt_password')

    return 0


def get_libvirt_connection(name, libvirt_url='qemu:///system'):
    if name not in LIBVIRT_CONNECTIONS:
        auth = [
            [libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_PASSPHRASE],
            auth_callback, None
        ]

        LIBVIRT_CONNECTIONS[name] = libvirt.openAuth(libvirt_url, auth)

    return LIBVIRT_CONNECTIONS[name]


def get_template(basename):
    """
    Load a file as a string from the templates directory

    Args:
        basename(str): filename

    Returns:
        str: string representation of the file
    """
    return pkg_resources.resource_string(
        __name__, '/'.join(['templates', basename])
    )


def dict_to_xml(spec, full_document=False):
    """
    Convert dict to XML

    Args:
        spec(dict): dict to convert
        full_document(bool): whether to add XML headers

    Returns:
        lxml.etree.Element: XML tree
    """

    middle = xmltodict.unparse(spec, full_document=full_document, pretty=True)
    return lxml.etree.fromstring(middle)
