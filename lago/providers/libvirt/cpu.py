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

import logging

from lxml import etree as ET

import lago.providers.libvirt.utils as utils
from lago.utils import LagoException, LagoInitException

LOGGER = logging.getLogger(__name__)


class CPU(object):
    def __init__(self, spec, host_cpu):
        """
        Generate CPU XML node.

        Args:
            spec(dict): VM Lago spec
            host_cpu(lxml.etree.Element): Host cpu capabilities
        """

        self.vcpu_set = False
        # TO-DO: deduce recommended defaults for vcpu_num from host CPU caps
        self.vcpu_num = '2'
        if spec.get('vcpu'):
            self.vcpu_set = True
            self.vcpu_num = spec['vcpu']
        self.cpu = spec.get('cpu_custom')
        self.cpu_model = spec.get('cpu_model')
        self.host_cpu = host_cpu
        self.validate()

        self._cpu_xml = self.generate_cpu_xml()
        self._vcpu_xml = self.generate_vcpu_xml(self.vcpu_num)

    def __iter__(self):
        for node in (self.cpu_xml, self.vcpu_xml):
            yield node

    def validate(self):
        """
        Validate CPU-related VM spec are compatible

        Raises:
            :exc:`~LagoInitException`: if both 'cpu_model' and 'cpu' are
                defined.
        """
        if self.cpu is not None and self.cpu_model:
            raise LagoInitException(
                'Defining both cpu_model and cpu_custom is '
                'not supported.'
            )

    @property
    def cpu_xml(self):
        return self._cpu_xml

    @property
    def vcpu_xml(self):
        return self._vcpu_xml

    @property
    def model(self):
        if self.cpu_model:
            return self.cpu_model
        elif not self.cpu:
            return self.host_cpu.xpath('model')[0].text
        else:
            return self._cpu_xml.xpath('model')[0].text

    @property
    def vendor(self):
        if self.cpu_model:
            return LibvirtCPU.get_cpu_vendor(self.cpu_model)
        elif not self.cpu:
            return self.host_cpu.xpath('vendor')[0].text
        else:
            return LibvirtCPU.get_cpu_vendor(self.model)

    def generate_cpu_xml(self):
        """
        Get CPU XML

        Returns:
            lxml.etree.Element: cpu node
        """
        if self.cpu:
            return self.generate_custom(
                cpu=self.cpu,
                vcpu_num=self.vcpu_num,
                fill_topology=self.vcpu_set
            )
        elif self.cpu_model:
            return self.generate_exact(
                self.cpu_model, vcpu_num=self.vcpu_num, host_cpu=self.host_cpu
            )
        else:
            return self.generate_host_passthrough(self.vcpu_num)

    def generate_vcpu_xml(self, vcpu_num):
        """
        generate_vcpu_xml

        Args:
            vcpu_num(int): number of virtual cpus

        Returns:
            lxml.etree.Element: vcpu XML node
        """

        return self.generate_vcpu(vcpu_num=self.vcpu_num)

    def generate_host_passthrough(self, vcpu_num):
        """
        Generate host-passthrough XML cpu node

        Args:
            vcpu_num(int): number of virtual CPUs

        Returns:
            lxml.etree.Element: CPU XML node
        """

        cpu = ET.Element('cpu', mode='host-passthrough')
        cpu.append(self.generate_topology(vcpu_num))
        return cpu

    def generate_custom(self, cpu, vcpu_num, fill_topology):
        """
        Generate custom CPU model. This method attempts to convert the dict to
        XML, as defined by ``xmltodict.unparse`` method.

        Args:
            cpu(dict): CPU spec
            vcpu_num(int): number of virtual cpus
            fill_topology(bool): if topology is not defined in ``cpu`` and
                ``vcpu`` was not set, will add CPU topology to the generated
                CPU.

        Returns:
            lxml.etree.Element: CPU XML node

        Raises:
            :exc:`~LagoInitException`: when failed to convert dict to XML
        """

        try:
            cpu = utils.dict_to_xml({'cpu': cpu})
        except:
            # TO-DO: print an example here
            raise LagoInitException('conversion of \'cpu\' to XML failed')

        if not cpu.xpath('topology') and fill_topology:
            cpu.append(self.generate_topology(vcpu_num))
        return cpu

    def generate_exact(self, model, vcpu_num, host_cpu):
        """
        Generate exact CPU model with nested virtualization CPU feature.

        Args:
            model(str): libvirt supported CPU model
            vcpu_num(int): number of virtual cpus
            host_cpu(lxml.etree.Element): the host CPU model

        Returns:
            lxml.etree.Element: CPU XML node
        """

        nested = {'Intel': 'vmx', 'AMD': 'svm'}
        cpu = ET.Element('cpu', match='exact')
        ET.SubElement(cpu, 'model').text = model
        cpu.append(self.generate_topology(vcpu_num))

        vendor = host_cpu.findtext('vendor')
        if not nested.get(vendor):
            LOGGER.debug(
                'Unknown vendor: {0}, did not configure nested '
                'virtualization cpu flag on guest.'.format(vendor)
            )
            return cpu

        model_vendor = LibvirtCPU.get_cpu_vendor(family=model)
        if vendor != model_vendor:
            LOGGER.debug(
                (
                    'Not enabling nested virtualization feature, host '
                    'vendor is: {0}, guest vendor: '
                    '{1}'.format(vendor, model_vendor)
                )
            )
            return cpu

        flag = nested[vendor]
        if host_cpu.find('feature/[@name="{0}"]'.format(flag)) is not None:
            cpu.append(self.generate_feature(name=flag))
        else:
            LOGGER.debug(
                (
                    'missing {0} cpu flag on host, nested '
                    'virtualization will probably not '
                    'work.'
                ).format(flag)
            )

        return cpu

    def generate_topology(self, vcpu_num, cores=1, threads=1):
        """
        Generate CPU <topology> XML child

        Args:
            vcpu_num(int): number of virtual CPUs
            cores(int): number of cores
            threads(int): number of threads

        Returns:
            lxml.etree.Element: topology XML element
        """

        return ET.Element(
            'topology',
            sockets=str(vcpu_num),
            cores=str(cores),
            threads=str(threads),
        )

    def generate_vcpu(self, vcpu_num):
        """
        Generate <vcpu> domain XML child

        Args:
            vcpu_num(int): number of virtual cpus

        Returns:
            lxml.etree.Element: vcpu XML element
        """

        vcpu = ET.Element('vcpu')
        vcpu.text = str(vcpu_num)
        return vcpu

    def generate_feature(self, name, policy='require'):
        """
        Generate CPU feature element

        Args:
            name(str): feature name
            policy(str): libvirt feature policy

        Returns:
            lxml.etree.Element: feature XML element
        """

        return ET.Element('feature', policy=policy, name=name)


class LibvirtCPU(object):
    """Query data from /usr/share/libvirt/cpu_map.xml"""

    @classmethod
    def get_cpu_vendor(cls, family, arch='x86'):
        """
        Get CPU vendor, if vendor is not available will return 'generic'

        Args:
            family(str): CPU family
            arch(str): CPU arch

        Returns:
            str: CPU vendor if found otherwise 'generic'
        """

        props = cls.get_cpu_props(family, arch)
        vendor = 'generic'
        try:
            vendor = props.xpath('vendor/@name')[0]
        except IndexError:
            pass
        return vendor

    @classmethod
    def get_cpu_props(cls, family, arch='x86'):
        """
        Get CPU info XML

        Args:
            family(str): CPU family
            arch(str): CPU arch

        Returns:
            lxml.etree.Element: CPU xml

        Raises:
            :exc:`~LagoException`: If no such CPU family exists
        """

        cpus = cls.get_cpus_by_arch(arch)
        try:
            return cpus.xpath('model[@name="{0}"]'.format(family))[0]
        except IndexError:
            raise LagoException('No such CPU family: {0}'.format(family))

    @classmethod
    def get_cpus_by_arch(cls, arch):
        """
        Get all CPUs info by arch

        Args:
            arch(str): CPU architecture

        Returns:
            lxml.etree.element: CPUs by arch XML

        Raises:
            :exc:`~LagoException`: If no such ARCH is found
        """

        with open('/usr/share/libvirt/cpu_map.xml', 'r') as cpu_map:
            cpu_xml = ET.parse(cpu_map)
        try:
            return cpu_xml.xpath('/cpus/arch[@name="{0}"]'.format(arch))[0]
        except IndexError:
            raise LagoException('No such arch: {0}'.format(arch))
