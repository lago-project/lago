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
import os
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
        self.cpu_custom = spec.get('cpu_custom')
        self.cpu_model = spec.get('cpu_model')
        self.host_cpu = host_cpu
        self.memory = spec.get('memory')
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
            :exc:`~LagoInitException`: if both 'cpu_model' and 'cpu_custom' are
                defined.
        """
        if self.cpu_custom is not None and self.cpu_model:
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
        elif not self.cpu_custom:
            return self.host_cpu.xpath('model')[0].text
        else:
            return self._cpu_xml.xpath('model')[0].text

    @property
    def vendor(self):
        if self.cpu_model:
            return LibvirtCPU.get_cpu_vendor(self.cpu_model)
        elif not self.cpu_custom:
            return self.host_cpu.xpath('vendor')[0].text
        else:
            return LibvirtCPU.get_cpu_vendor(self.model)

    def generate_cpu_xml(self):
        """
        Get CPU XML

        Returns:
            lxml.etree.Element: cpu node
        """
        if self.cpu_custom:
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
            vcpu_num(str): number of virtual CPUs

        Returns:
            lxml.etree.Element: CPU XML node
        """

        cpu = ET.Element('cpu', mode='host-passthrough')
        cpu.append(self.generate_topology(vcpu_num))
        if vcpu_num > 1:
            cpu.append(self.generate_numa(vcpu_num))
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
            vcpu_num(str): number of virtual CPUs
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

    def generate_numa(self, vcpu_num):
        """
        Generate guest CPU <numa> XML child
        Configures 1, 2 or 4 vCPUs per cell.

        Args:
            vcpu_num(str): number of virtual CPUs

        Returns:
            lxml.etree.Element: numa XML element
        """

        if int(vcpu_num) == 2:
            # 2 vCPUs is a special case.
            # We wish to have 2 cells,
            # with 1 vCPU in each.
            # This is also the common case.
            total_cells = 2
            cpus_per_cell = 1
        elif int(vcpu_num) == 4:
            # 4 vCPU is a special case.
            # We wish to have 2 cells,
            # with 2 vCPUs in each.
            total_cells = 2
            cpus_per_cell = 2
        else:
            cell_info = divmod(int(vcpu_num), 4)
            if cell_info[1] == 0:
                # 4 vCPUs in each cell
                total_cells = cell_info[0]
                cpus_per_cell = 4
            elif cell_info[1] == 2:
                # 2 vCPUs in each cell
                total_cells = (cell_info[0] * 2) + 1
                cpus_per_cell = 2
            else:
                # 1 vCPU per cell...
                total_cells = int(vcpu_num)
                cpus_per_cell = 1

        numa = ET.Element('numa')
        memory_per_cell = divmod(int(self.memory), total_cells)
        LOGGER.debug(
            'numa\n: cpus_per_cell: {0}, total_cells: {1}'.format(
                cpus_per_cell, total_cells
            )
        )
        for cell_id in xrange(0, total_cells):
            first_cpu_in_cell = cell_id * cpus_per_cell
            if cpus_per_cell == 1:
                cpus_in_cell = str(first_cpu_in_cell)
            else:
                cpus_in_cell = '{0}-{1}'.format(
                    first_cpu_in_cell, first_cpu_in_cell + cpus_per_cell - 1
                )
            cell = ET.Element(
                'cell',
                id=str(cell_id),
                cpus=cpus_in_cell,
                memory=str(memory_per_cell[0]),
                unit='MiB',
            )
            numa.append(cell)

        LOGGER.debug('numa:\n{}'.format(ET.tostring(numa, pretty_print=True)))
        return numa

    def generate_vcpu(self, vcpu_num):
        """
        Generate <vcpu> domain XML child

        Args:
            vcpu_num(str): number of virtual cpus

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

        cpu_map_xml = "/usr/share/libvirt/cpu_map.xml"
        cpu_map_dir = "/usr/share/libvirt/cpu_map/"
        cpu_map_index_xml = cpu_map_dir + "index.xml"
        if not os.path.exists(cpu_map_xml):
            cpu_xml = ET.ElementTree(
                ET.fromstring(create_xml_map(cpu_map_index_xml, cpu_map_dir))
            )
        else:
            with open(cpu_map_xml, 'r') as cpu_map:
                cpu_xml = ET.parse(cpu_map)
        try:
            return cpu_xml.xpath('/cpus/arch[@name="{0}"]'.format(arch))[0]
        except IndexError:
            raise LagoException('No such arch: {0}'.format(arch))


def create_xml_map(cpu_map_index_xml, cpu_map_dir):
    xml_list = []
    if os.path.exists(cpu_map_index_xml):
        with open(cpu_map_index_xml) as fp:
            line = fp.readline()
            while line:
                if "include" in line:
                    tree = ET.fromstring(line)
                    for child in tree.getiterator():
                        if child.tag == "include":
                            filename = child.attrib["filename"]
                            with open(
                                cpu_map_dir + filename, 'r'
                            ) as content_file:
                                for content_line in content_file:
                                    if "cpus" not in content_line:
                                        xml_list.append(content_line)
                else:
                    xml_list.append(line)
                line = fp.readline()
    return ''.join(xml_list)
