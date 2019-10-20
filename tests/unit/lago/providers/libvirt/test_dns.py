#
# Copyright 2017 Red Hat, Inc.
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
import lxml.etree as ET
from xmlunittest import XmlTestCase

from lago.providers.libvirt.network import LibvirtDNS


class TestDNS(XmlTestCase):
    def test_dns_disable(self):
        _xml = '<dns enable="no" />'
        dns = LibvirtDNS.generate_dns_disable()

        self.assertXmlEquivalentOutputs(ET.tostring(dns), _xml)

    def test_default_dns(self):
        _xml = '<dns enable="yes" forwardPlainNames="yes" />'
        dns = LibvirtDNS.generate_default_dns()

        self.assertXmlEquivalentOutputs(ET.tostring(dns), _xml)

    def test_forward_dns(self):
        _xml = """
        <dns enable="yes" forwardPlainNames="yes">
            <forwarder addr="8.8.8.8" />
        </dns>
        """

        dns = LibvirtDNS.generate_dns_forward([{'addr': '8.8.8.8'}])

        self.assertXmlEquivalentOutputs(ET.tostring(dns), _xml)

    def test_main_dns(self):
        _xml = """
        <dns enable="yes" forwardPlainNames="yes">
            <host ip="192.168.122.2">
                <hostname>myhost</hostname>
                <hostname>myhostalias</hostname>
            </host>
            <forwarder addr="8.8.8.8" />
            <forwarder addr="8.8.4.4" domain="example.com" />
        </dns>
        """

        records = [
            ('myhost', '192.168.122.2'), ('myhostalias', '192.168.122.2')
        ]

        forwarders = [
            {
                'addr': '8.8.8.8'
            }, {
                'addr': '8.8.4.4',
                'domain': 'example.com'
            }
        ]

        dns = LibvirtDNS.generate_main_dns(records, forwarders, True)

        self.assertXmlEquivalentOutputs(ET.tostring(dns), _xml)
