#!/usr/bin/env python3
#
# MIT License
#
# Copyright (c) 2023 FABRIC Testbed
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.
from ipaddress import IPv4Network

from fabrictestbed_extensions.fablib.fablib import fablib

from tests.base_test import BaseTest


class MflibSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "MflibSlice"
        super(MflibSliceTest, self).setUp()

    def test_slice(self):
        [site1] = fablib.get_random_sites(count=1)
        print(f"Sites: {site1}")

        node1_name = 'Node1'
        network1_name = 'net1'

        # Create a slice with one node connected to a network
        # Networks
        net1 = self._slice.add_l2network(name=network1_name, subnet=IPv4Network("192.168.1.0/24"))

        # Node1
        print(f"Adding Node1: {node1_name}")
        node1 = self._slice.add_node(name=node1_name, site=site1)
        interface1 = node1.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        interface1.set_mode('auto')
        net1.add_interface(interface1)
        self._slice.submit()

        self.check_slice(node_cnt=1, network_cnt=1)

        self._slice.update()

        # Add measurement node
        self._slice.add_node(name=f"MeasNode-{site1}", site=site1)

        # Connect user slice nodes to measurement node via FabNet
        interfaces_per_site = {}
        for n in self._slice.get_nodes():
            interface = n.add_component(model='NIC_Basic', name='L3-nic').get_interfaces()[0]
            interface.set_mode('auto')
            if n.get_site() not in interfaces_per_site:
                interfaces_per_site[n.get_site()] = []
            interfaces_per_site[n.get_site()].append(interface)

        for site, interfaces in interfaces_per_site.items():
            self._slice.add_l3network(name=f"{site}-L3", interfaces=interfaces)

        self._slice.submit()

        self.check_slice(node_cnt=2, network_cnt=len(interfaces_per_site) + 1)

        self._slice.delete()
