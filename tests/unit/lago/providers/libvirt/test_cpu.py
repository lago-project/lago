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

from itertools import permutations

import lxml.etree as ET
import pytest
from xmlunittest import XmlTestCase

from lago.providers.libvirt import cpu
from lago.utils import LagoInitException


class TestCPU(XmlTestCase):
    def get_host_cpu(self, arch='x86_64', model='Westmere', vendor='Intel'):
        return ET.fromstring(
            """
                             <cpu>
                                   <arch>{arch}</arch>
                                   <model>{model}</model>
                                   <vendor>{vendor}</vendor>
                             </cpu>
                             """.format(arch=arch, model=model, vendor=vendor)
        )

    def test_generate_topology(self):
        _xml = """
        <topology sockets="{vcpu_num}" cores="{cores}" threads="{threads}" />
        """
        combs = [
            {
                'vcpu_num': tup[0],
                'cores': tup[1],
                'threads': tup[2]
            } for tup in permutations(range(1, 4), 3)
        ]

        empty_cpu = cpu.CPU(spec={}, host_cpu=None)
        for comb in combs:
            self.assertXmlEquivalentOutputs(
                ET.tostring(empty_cpu.generate_topology(**comb)),
                _xml.format(**comb)
            )

    def test_generate_host_passthrough(self):
        _xml = """
        <cpu mode="host-passthrough">
            <topology sockets="{0}" cores="1" threads="1"/>
        </cpu>
        """
        empty_cpu = cpu.CPU(spec={}, host_cpu=None)
        for vcpu_num in [1, 9, 11, 120]:
            self.assertXmlEquivalentOutputs(
                ET.tostring(empty_cpu.generate_host_passthrough(vcpu_num)),
                _xml.format(vcpu_num)
            )

    def test_generate_exact_intel_vmx_intel_vmx(self, vcpu=2, model='Penryn'):

        _xml = """
        <cpu match="exact">
            <model>{model}</model>
            <topology cores="1" sockets="{vcpu}" threads="1"/>
            <feature policy="require" name="vmx"/>
        </cpu>
        """.format(
            vcpu=vcpu, model=model
        )
        host = ET.fromstring(
            """
                             <cpu>
                                   <arch>x86_64</arch>
                                   <model>Westmere</model>
                                   <vendor>Intel</vendor>
                                   <feature name='vmx'/>
                             </cpu>
                             """
        )
        empty_cpu = cpu.CPU(spec={}, host_cpu=None)
        self.assertXmlEquivalentOutputs(
            ET.tostring(
                empty_cpu.
                generate_exact(model=model, vcpu_num=vcpu, host_cpu=host)
            ), _xml
        )

    def test_generate_exact_intel_novmx(self, vcpu=2, model='Penryn'):

        _xml = """
        <cpu match="exact">
            <model>{model}</model>
            <topology cores="1" sockets="{vcpu}" threads="1"/>
        </cpu>
        """.format(
            vcpu=vcpu, model=model
        )
        host = ET.fromstring(
            """
                             <cpu>
                                   <arch>x86_64</arch>
                                   <model>Westmere</model>
                                   <vendor>Intel</vendor>
                             </cpu>
                             """
        )
        empty_cpu = cpu.CPU(spec={}, host_cpu=None)
        self.assertXmlEquivalentOutputs(
            ET.tostring(
                empty_cpu.
                generate_exact(model=model, vcpu_num=vcpu, host_cpu=host)
            ), _xml
        )

    def test_generate_exact_vendor_mismatch(self, vcpu=2, model='Opteron_G2'):

        _xml = """
        <cpu match="exact">
            <model>{model}</model>
            <topology cores="1" sockets="{vcpu}" threads="1"/>
        </cpu>
        """.format(
            vcpu=vcpu, model=model
        )
        host = ET.fromstring(
            """
                             <cpu>
                                   <arch>x86_64</arch>
                                   <model>Westmere</model>
                                   <vendor>Intel</vendor>
                             </cpu>
                             """
        )
        empty_cpu = cpu.CPU(spec={}, host_cpu=None)
        self.assertXmlEquivalentOutputs(
            ET.tostring(
                empty_cpu.
                generate_exact(model=model, vcpu_num=vcpu, host_cpu=host)
            ), _xml
        )

    def test_generate_exact_unknown_vendor(self, vcpu=2, model='Westmere'):

        _xml = """
        <cpu match="exact">
            <model>{model}</model>
            <topology cores="1" sockets="{vcpu}" threads="1"/>
        </cpu>
        """.format(
            vcpu=vcpu, model=model
        )
        host = ET.fromstring(
            """
                             <cpu>
                                   <arch>ppc64</arch>
                                   <model>Power6</model>
                                   <vendor>IBM</vendor>
                             </cpu>
                             """
        )
        empty_cpu = cpu.CPU(spec={}, host_cpu=None)
        self.assertXmlEquivalentOutputs(
            ET.tostring(
                empty_cpu.
                generate_exact(model=model, vcpu_num=vcpu, host_cpu=host)
            ), _xml
        )

    def test_init_default(self):
        spec = {}
        _xml = """
        <cpu mode="host-passthrough">
            <topology sockets="2" cores="1" threads="1"/>
        </cpu>
        """
        def_cpu = cpu.CPU(spec=spec, host_cpu=self.get_host_cpu())
        self.assertXmlEquivalentOutputs(ET.tostring(def_cpu.cpu_xml), _xml)

    def test_init_custom_and_model_not_allowed(self):
        spec = {'cpu_custom': 'custom', 'cpu_model': 'DummyModel'}
        with pytest.raises(LagoInitException):
            cpu.CPU(spec=spec, host_cpu=self.get_host_cpu())
