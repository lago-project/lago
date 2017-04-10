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

import functools
import logging
import time
from copy import deepcopy

from lxml import etree as ET

import lago.providers.libvirt.utils as libvirt_utils
from lago import brctl, log_utils, utils
from lago.config import config

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)


class Network(object):
    def __init__(self, env, spec):
        self._env = env
        libvirt_url = config.get('libvirt_url')
        self.libvirt_con = libvirt_utils.get_libvirt_connection(
            name=env.uuid + libvirt_url,
            libvirt_url=libvirt_url,
        )
        self._spec = spec

    def name(self):
        return self._spec['name']

    def gw(self):
        return self._spec.get('gw')

    def is_management(self):
        return self._spec.get('management', False)

    def add_mappings(self, mappings):
        for name, ip, mac in mappings:
            self.add_mapping(name, ip, save=False)
        self.save()

    def add_mapping(self, name, ip, save=True):
        self._spec['mapping'][name] = ip
        if save:
            self.save()

    def resolve(self, name):
        return self._spec['mapping'][name]

    def mapping(self):
        return self._spec['mapping']

    def _libvirt_name(self):
        return self._env.prefixed_name(self.name(), max_length=15)

    def _libvirt_xml(self):
        raise NotImplementedError(
            'should be implemented by the specific network class'
        )

    def alive(self):
        net_names = [net.name() for net in self.libvirt_con.listAllNetworks()]
        return self._libvirt_name() in net_names

    def start(self, attempts=5, timeout=2):
        """
        Start the network, will check if the network is active ``attempts``
        times, waiting ``timeout`` between each attempt.

        Args:
            attempts (int): number of attempts to check the network is active
            timeout  (int): timeout for each attempt

        Returns:
            None

        Raises:
            RuntimeError: if network creation failed, or failed to verify it is
            active.
        """

        if not self.alive():
            with LogTask('Create network %s' % self.name()):
                net = self.libvirt_con.networkCreateXML(self._libvirt_xml())
                if net is None:
                    raise RuntimeError(
                        'failed to create network, XML: %s' %
                        (self._libvirt_xml())
                    )
                for _ in range(attempts):
                    if net.isActive():
                        return
                    LOGGER.debug(
                        'waiting for network %s to become active', net.name()
                    )
                    time.sleep(timeout)
                raise RuntimeError(
                    'failed to verify network %s is active' % net.name()
                )

    def stop(self):
        if self.alive():
            with LogTask('Destroy network %s' % self.name()):
                self.libvirt_con.networkLookupByName(
                    self._libvirt_name(),
                ).destroy()

    def save(self):
        with open(self._env.virt_path('net-%s' % self.name()), 'w') as f:
            utils.json_dump(self._spec, f)

    @property
    def spec(self):
        return deepcopy(self._spec)


class NATNetwork(Network):
    def _libvirt_xml(self):
        net_raw_xml = libvirt_utils.get_template('net_nat_template.xml')

        subnet = self.gw().split('.')[2]
        replacements = {
            '@NAME@':
                self._libvirt_name(),
            '@BR_NAME@': ('%s-nic' % self._libvirt_name())[:12],
            '@GW_ADDR@':
                self.gw(),
            '@SUBNET@':
                subnet,
            '@ENABLE_DNS@':
                'yes' if self._spec.get('enable_dns', True) else 'no',
        }
        for k, v in replacements.items():
            net_raw_xml = net_raw_xml.replace(k, v, 1)

        net_xml = ET.fromstring(net_raw_xml)
        dns_domain_name = self._spec.get('dns_domain_name', None)
        if dns_domain_name is not None:
            domain_xml = ET.Element(
                'domain',
                name=dns_domain_name,
                localOnly='yes',
            )
            net_xml.append(domain_xml)
        if 'dhcp' in self._spec:
            IPV6_PREFIX = 'fd8f:1391:3a82:' + subnet + '::'
            ipv4 = net_xml.xpath('/network/ip')[0]
            ipv6 = net_xml.xpath('/network/ip')[1]
            dns = net_xml.xpath('/network/dns')[0]

            def make_ipv4(last):
                return '.'.join(self.gw().split('.')[:-1] + [str(last)])

            dhcp = ET.Element('dhcp')
            dhcpv6 = ET.Element('dhcp')
            ipv4.append(dhcp)
            ipv6.append(dhcpv6)

            dhcp.append(
                ET.Element(
                    'range',
                    start=make_ipv4(self._spec['dhcp']['start']),
                    end=make_ipv4(self._spec['dhcp']['end']),
                )
            )
            dhcpv6.append(
                ET.Element(
                    'range',
                    start=IPV6_PREFIX + make_ipv4(self._spec['dhcp']['start']),
                    end=IPV6_PREFIX + make_ipv4(self._spec['dhcp']['end']),
                )
            )

            if self.is_management():
                for hostname, ip4 in self._spec['mapping'].items():
                    dhcp.append(
                        ET.Element(
                            'host',
                            mac=utils.ipv4_to_mac(ip4),
                            ip=ip4,
                            name=hostname
                        )
                    )
                    dhcpv6.append(
                        ET.Element(
                            'host',
                            id='0:3:0:1:' + utils.ipv4_to_mac(ip4),
                            ip=IPV6_PREFIX + ip4,
                            name=hostname
                        )
                    )
                    dns_host = ET.SubElement(dns, 'host', ip=ip4)
                    dns_name = ET.SubElement(dns_host, 'hostname')
                    dns_name.text = hostname
                    dns6_host = ET.SubElement(
                        dns, 'host', ip=IPV6_PREFIX + ip4
                    )
                    dns6_name = ET.SubElement(dns6_host, 'hostname')
                    dns6_name.text = hostname
                    dns.append(dns_host)
                    dns.append(dns6_host)

        return ET.tostring(net_xml)


class BridgeNetwork(Network):
    def _libvirt_xml(self):
        net_raw_xml = libvirt_utils.get_template('net_br_template.xml')

        replacements = {
            '@NAME@': self._libvirt_name(),
            '@BR_NAME@': self._libvirt_name(),
        }
        for k, v in replacements.items():
            net_raw_xml = net_raw_xml.replace(k, v, 1)

        return net_raw_xml

    def start(self):
        if brctl.exists(self._libvirt_name()):
            return

        brctl.create(self._libvirt_name())
        try:
            super(BridgeNetwork, self).start()
        except:
            brctl.destroy(self._libvirt_name())

    def stop(self):
        super(BridgeNetwork, self).stop()
        if brctl.exists(self._libvirt_name()):
            brctl.destroy(self._libvirt_name())
