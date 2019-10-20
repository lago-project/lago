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
from future.builtins import super
from collections import defaultdict
import functools
import itertools
import logging
import time
from copy import deepcopy

from lxml import etree as ET
import lago.providers.libvirt.utils as libvirt_utils
from lago import brctl, log_utils, utils
import libvirt

LOGGER = logging.getLogger(__name__)
LogTask = functools.partial(log_utils.LogTask, logger=LOGGER)


class Network(object):
    def __init__(self, env, spec, compat):
        self._env = env
        self.libvirt_con = libvirt_utils.get_libvirt_connection(
            name=env.uuid,
        )
        self._spec = spec
        self.compat = compat

    def __del__(self):
        if self.libvirt_con is not None:
            self.libvirt_con.close()

    def name(self):
        return self._spec['name']

    def gw(self):
        return self._spec.get('gw')

    @property
    def subnet(self):
        return self.gw().split('.')[2]

    def mtu(self):
        if self.libvirt_con.getLibVersion() > 3001001:
            return self._spec.get('mtu', '1500')
        else:
            return '1500'

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
        flags = libvirt.VIR_CONNECT_LIST_NETWORKS_TRANSIENT \
            | libvirt.VIR_CONNECT_LIST_NETWORKS_ACTIVE
        net_names = [
            net.name() for net in self.libvirt_con.listAllNetworks(flags)
        ]
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


class LibvirtDNS(object):
    """
    This class represents the `dns` element in Libvirt's
    Network XML.

    This class has convenient "class methods" for generating
    specific dns elements.

    For more information please refer to Libvirt's documentation:
    https://libvirt.org/formatnetwork.html

    Attributes:
        _dns(lxml.etree.Element): The root of the `dns` element
    """

    def __init__(self, enable=True, forward_plain_names=True):
        """
        Args:
            enabled(bool): If false, don't create a dns server
            forward_plain_names(bool): If false, names that are not FQDNs
                will not be forwarded to the host's upstream server.
        """
        forward_plain_name = 'yes' if forward_plain_names else 'no'

        if enable:
            self._dns = ET.Element(
                'dns',
                enable='yes',
                forwardPlainNames=forward_plain_name,
            )
        else:
            self._dns = ET.Element('dns', enable='no')

    @classmethod
    def generate_dns_forward(cls, forwarders):
        """
        Generate a dns server that forwards request to one or more dns servers.

        Args:
            forwarders(list of dicts): Each dict represents a `forwarder`
                that will be added to the dns server. The dict's items
                will be added as attributes to the forwarder element.
        """
        dns = cls()
        dns.add_forwarders(*forwarders)

        return dns.get_xml_object()

    @classmethod
    def generate_dns_disable(cls):
        """
        Generate a disbaled dns server.
        """
        dns = cls(enable=False)

        return dns.get_xml_object()

    @classmethod
    def generate_default_dns(cls):
        """
        Generate a default dns server.
        Please refer to the default values of the `__init__` method
        in order to see the properties of a default dns server.
        """
        return cls().get_xml_object()

    @classmethod
    def generate_main_dns(cls, records, forwarders, forward_plain_names):
        """
        Generate a dns server for Lago's management network.

        Args:
            records(list of tuples): For a tuple "t", t[0] is a hostname
                and t[1] is its IP. Each tuple will be added as a `host`
                element to the dns server.
            forwarders(list of dicts): List of forwarders that will be added
                ths dns server.
            forward_plain_name(bool): If false, names that are not
                FQDNs will not be forwarded to the host's upstream server.
        """
        dns = cls(forward_plain_names=forward_plain_names)

        reverse_records = defaultdict(list)
        for hostname, ip in records:
            reverse_records[ip] = reverse_records[ip] + [hostname]

        for ip, hostnames in reverse_records.iteritems():
            dns.add_host(ip, *hostnames)

        dns.add_forwarders(*forwarders)

        return dns.get_xml_object()

    def add_forwarders(self, *forwarders):
        """
        Add `forwarder(s)` to the dns server.

        Args:
            forwarders(dicts): One or more dicts that represents a forwader.
                Each item in the dict will be mapped to an attribute of
                the forwarder.
        """
        for forwarder in forwarders:
            self._dns.append(ET.Element('forwarder', **forwarder))

    def add_host(self, ip, *hostnames):
        """
        Add `host entry(s)` to the dns server.

        Args:
            ip(str): The host's IP address.
            hostnames(str): One or more hostnames that will be mapped to `ip`.
        """
        host_element = ET.Element('host', ip=ip)

        for hostname in sorted(hostnames):
            hostname_element = ET.Element('hostname')
            hostname_element.text = hostname
            host_element.append(hostname_element)

        self._dns.append(host_element)

    def get_xml_object(self):
        """
        Returns:
            (lxml.etree.Element): The dns server
        """
        return deepcopy(self._dns)


class NATNetwork(Network):
    def _ipv6_prefix(self, subnet, const='fd8f:1391:3a82:'):
        return '{0}{1}::'.format(const, subnet)

    def get_ipv6_dns_records(self, mapping):
        """
        Given a mapping between host names and an IPv4 addresses,
        return a new mapping from hostnames and their IPv6.
        The IPv6 address is gernerate from the host's IPv4.

        Args:
            mapping(dict): A mapping between host names and their
                IPv4 addresses.

        Returns:
            (dict): A mapping between host names and their IPv6 addresses.
        """
        return {
            hostname: self.ipv6_prefix + ip
            for hostname, ip in mapping.items()
        }

    def get_ipv4_and_ipv6_dns_records(self, mapping_name):
        """
        Get a chain of tuples that represent a mapping between a hostname
        and its IP address. The chain will include tuples for IPv4 and IPv6
        addresses.

        Args:
            mapping_name(str): From which dict of this network spec the chain
                should be built.

        Returns:
            (itertools.chain): A chain of tuples.
        """
        return itertools.chain(
            self.spec[mapping_name].iteritems(),
            self.get_ipv6_dns_records(self.spec[mapping_name]).iteritems(),
        )

    @property
    def ipv6_prefix(self):
        return self._ipv6_prefix(self.subnet)

    def _libvirt_xml(self):
        net_raw_xml = libvirt_utils.get_template('net_nat_template.xml')
        mtu = self.mtu()

        replacements = {
            '@NAME@': self._libvirt_name(),
            '@BR_NAME@': ('%s-nic' % self._libvirt_name())[:12],
            '@GW_ADDR@': self.gw(),
            '@SUBNET@': self.subnet
        }
        for k, v in replacements.items():
            net_raw_xml = net_raw_xml.replace(k, v, 1)

        parser = ET.XMLParser(remove_blank_text=True)
        net_xml = ET.fromstring(net_raw_xml, parser)

        if mtu != '1500':
            net_xml.append(ET.Element(
                'mtu',
                size=str(mtu),
            ))
        if 'dhcp' in self._spec:
            ipv4 = net_xml.xpath('/network/ip')[0]
            ipv6 = net_xml.xpath('/network/ip')[1]

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
                    start=self.ipv6_prefix +
                    make_ipv4(self._spec['dhcp']['start']),
                    end=self.ipv6_prefix +
                    make_ipv4(self._spec['dhcp']['end']),
                )
            )

            ipv4s = []
            for hostname in sorted(self._spec['mapping'].iterkeys()):
                ip4 = self._spec['mapping'][hostname]
                if ip4 in ipv4s:
                    continue

                ipv4s.append(ip4)
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
                        ip=self.ipv6_prefix + ip4,
                        name=hostname
                    )
                )

        if utils.ver_cmp(self.compat, '0.36.11') >= 0:
            if self.is_management():
                domain_xml = ET.Element(
                    'domain',
                    name=self._spec['dns_domain_name'],
                    localOnly='yes'
                )
                net_xml.append(domain_xml)

                net_xml.append(
                    LibvirtDNS.generate_main_dns(
                        self.get_ipv4_and_ipv6_dns_records('dns_records'),
                        self._spec.get('dns_forwarders', []),
                        forward_plain_names=False
                    )
                )
            else:
                if self.libvirt_con.getLibVersion() < 2002000:
                    net_xml.append(
                        LibvirtDNS.generate_dns_forward(
                            self._spec['dns_forwarders']
                        )
                    )
                else:
                    net_xml.append(LibvirtDNS.generate_dns_disable())
        else:
            LOGGER.debug(
                'Generating network XML with compatibility prior to %s',
                self.compat
            )
            # Prior to v0.37, DNS records were only the  mappings of the
            # management network.
            if self.is_management():
                if 'dns_domain_name' in self._spec:
                    domain_xml = ET.Element(
                        'domain',
                        name=self._spec['dns_domain_name'],
                        localOnly='yes'
                    )
                    net_xml.append(domain_xml)

                dns_element = LibvirtDNS.generate_main_dns(
                    self.get_ipv4_and_ipv6_dns_records('mapping'),
                    [],
                    forward_plain_names=True,
                )

                net_xml.append(dns_element)
            else:
                net_xml.append(LibvirtDNS.generate_default_dns())

        LOGGER.debug(
            'Generated Network XML\n {0}'.format(
                ET.tostring(net_xml, pretty_print=True)
            )
        )
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
            super().start()
        except:
            brctl.destroy(self._libvirt_name())

    def stop(self):
        super().stop()
        if brctl.exists(self._libvirt_name()):
            brctl.destroy(self._libvirt_name())
