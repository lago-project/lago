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
import xmltodict
import lxml.etree
import logging
import pkg_resources
from jinja2 import Environment, PackageLoader, TemplateNotFound
from lago.utils import LagoException
from lago.config import config

LOGGER = logging.getLogger(__name__)

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
LIBVIRT_CONNECTION = None
LIBVIRT_CONN_COUNTER = 0
LIBVIRT_VER = None
LIBVIRT_CAPS = None
QEMU_KVM_PATH = None


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


def get_libvirt_connection(libvirt_url='qemu:///system'):
    global LIBVIRT_CONNECTION
    global LIBVIRT_VERSION
    global LIBVIRT_CAPS
    global LIBVIRT_CONN_COUNTER
    global QEMU_KVM_PATH
    if LIBVIRT_CONNECTION is None:
        auth = [
            [libvirt.VIR_CRED_AUTHNAME, libvirt.VIR_CRED_PASSPHRASE],
            auth_callback, None
        ]
        LIBVIRT_CONNECTION = libvirt.openAuth(libvirt_url, auth)
        LIBVIRT_VERSION = LIBVIRT_CONNECTION.getLibVersion()
        caps_raw_xml = LIBVIRT_CONNECTION.getCapabilities()
        LIBVIRT_CAPS = lxml.etree.fromstring(caps_raw_xml)
        _qemu_kvm_path = LIBVIRT_CAPS.findtext(
            "guest[os_type='hvm']/arch[@name='x86_64']/domain[@type='kvm']"
            "/emulator"
        )
        if not _qemu_kvm_path:
            LOGGER.warning("hardware acceleration not available")
            _qemu_kvm_path = LIBVIRT_CAPS.findtext(
                "guest[os_type='hvm']/arch[@name='x86_64']"
                "/domain[@type='qemu']/../emulator"
            )

        if not _qemu_kvm_path:
            raise LagoException('kvm executable not found')
        QEMU_KVM_PATH = _qemu_kvm_path

    LIBVIRT_CONN_COUNTER += 1
    return LIBVIRT_CONNECTION


def close_libvirt_connection():
    global LIBVIRT_CONNECTION
    global LIBVIRT_CONN_COUNTER
    LIBVIRT_CONN_COUNTER -= 1
    if LIBVIRT_CONN_COUNTER == 0:
        LIBVIRT_CONNECTION.close()


def get_libvirt_version():
    return LIBVIRT_VERSION


def get_libvirt_caps():
    return LIBVIRT_CAPS


def get_qemu_kvm_path():
    return QEMU_KVM_PATH


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


def get_domain_template(distro, libvirt_ver, **kwargs):
    """
    Get a rendered Jinja2 domain template

    Args:
        distro(str): domain distro
        libvirt_ver(int): libvirt version
        kwargs(dict): args for template render

    Returns:
        str: rendered template
    """
    env = Environment(
        loader=PackageLoader('lago', 'providers/libvirt/templates'),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    template_name = 'dom_template-{0}.xml.j2'.format(distro)
    try:
        template = env.get_template(template_name)
    except TemplateNotFound:
        LOGGER.debug('could not find template %s using default', template_name)
        template = env.get_template('dom_template-base.xml.j2')
    return template.render(libvirt_ver=libvirt_ver, **kwargs)


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
