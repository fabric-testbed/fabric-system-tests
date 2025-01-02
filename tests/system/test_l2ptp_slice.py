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


class L2PTPSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "L2PTP"
        super(L2PTPSliceTest, self).setUp()

    def test_slice(self):
        [site1, site2, site3, site4] = ["ATLA", "WASH", "STAR", "NEWY"]
        node1_name = 'Node1'
        node2_name = 'Node2'
        # Path1 : LOSA -> SALT -> NEWY
        # Path2 : LOSA -> DALL -> NEWY
        net1_name = 'net-with-ero-path1'
        net2_name = 'net-with-ero-path2'

        # Network
        net1 = self._slice.add_l2network(name=net1_name, subnet=IPv4Network("192.168.1.0/24"))

        net2 = self._slice.add_l2network(name=net2_name, subnet=IPv4Network("192.168.2.0/24"))

        # Node1
        node1 = self._slice.add_node(name=node1_name, site=site1)
        n1_nic1 = node1.add_component(model='NIC_ConnectX_5', name='nic1')
        n1_nic1.get_interfaces()[0].set_mode('auto')
        n1_nic1.get_interfaces()[0].set_vlan('100')
        n1_nic1.get_interfaces()[1].set_mode('auto')
        n1_nic1.get_interfaces()[1].set_vlan('200')

        net1.add_interface(n1_nic1.get_interfaces()[0])

        net2.add_interface(n1_nic1.get_interfaces()[1])

        # Node2
        node2 = self._slice.add_node(name=node2_name, site=site4)
        n2_nic1 = node2.add_component(model='NIC_ConnectX_5', name='nic1')

        n2_nic1.get_interfaces()[0].set_mode('auto')
        n2_nic1.get_interfaces()[0].set_vlan('100')
        n2_nic1.get_interfaces()[1].set_mode('auto')
        n2_nic1.get_interfaces()[1].set_vlan('200')

        net1.add_interface(n2_nic1.get_interfaces()[0])

        net2.add_interface(n2_nic1.get_interfaces()[1])

        # Set Explicit Route Options for Network1
        net1.set_l2_route_hops(hops=[site2])

        # Set Explicit Route Options for Network2
        net2.set_l2_route_hops(hops=[site3])

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=2, network_cnt=2)
        self.check_ping(node1=node1, node2=node2, network_name=net1_name)
        self.check_ping(node1=node1, node2=node2, network_name=net2_name)
        # VERIFICATION

        self._slice.delete()
