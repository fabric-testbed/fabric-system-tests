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
# Author: Komal Thareja (kthare10@renci.org)

from ipaddress import IPv4Network

from tests.base_test import BaseTest


class L2BridgeSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "L2Bridge"
        super(L2BridgeSliceTest, self).setUp()

    def test_slice(self):
        [site] = self._fablib.get_random_sites(count=1)
        print(f"Sites: {site}")

        node1_name = 'Node1'
        node2_name = 'Node2'

        network_name = 'net1'

        # Network
        net1 = self._slice.add_l2network(name=network_name, subnet=IPv4Network("192.168.1.0/24"))

        # Node1
        node1 = self._slice.add_node(name=node1_name, site=site)
        iface1 = node1.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface1.set_mode('auto')
        net1.add_interface(iface1)

        # Node2
        node2 = self._slice.add_node(name=node2_name, site=site)
        iface2 = node2.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface2.set_mode('auto')
        net1.add_interface(iface2)

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=2, network_cnt=1)
        self.check_ping(node1=node1, node2=node2, network_name=network_name)
        # VERIFICATION

        self._slice.delete()
