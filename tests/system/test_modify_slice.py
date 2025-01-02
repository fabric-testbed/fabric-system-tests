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

from fabrictestbed_extensions.fablib.fablib import fablib

from tests.base_test import BaseTest


class ModifySliceTest(BaseTest):
    def setUp(self):
        self.prefix = "Modify"
        super(ModifySliceTest, self).setUp()

    def test_slice(self):
        [site1, site2, site3] = fablib.get_random_sites(count=3)

        print(f"Sites: {site1}, {site2}, {site3}")

        node1_name = 'Node1'
        node2_name = 'Node2'
        node3_name = 'Node3'
        node4_name = 'Node4'

        network1_name = 'net1'
        network2_name = 'net2'
        network3_name = 'net3'

        # Networks
        net1 = self._slice.add_l2network(name=network1_name, subnet=IPv4Network("192.168.1.0/24"))

        # Node1
        node1 = self._slice.add_node(name=node1_name, site=site1)
        iface1 = node1.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface1.set_mode('auto')
        net1.add_interface(iface1)

        # Node2
        node2 = self._slice.add_node(name=node2_name, site=site2)
        iface2 = node2.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface2.set_mode('auto')
        net1.add_interface(iface2)

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=2, network_cnt=1)
        node1 = self._slice.get_node(name=node1_name)
        node2 = self._slice.get_node(name=node2_name)
        self.check_ping(node1=node1, node2=node2, network_name=network1_name)
        # VERIFICATION

        # Add a Layer2 Network
        net2 = self._slice.add_l2network(name=network2_name, subnet=IPv4Network("192.168.2.0/24"))

        # Add Node3
        node3 = self._slice.add_node(name=node3_name, site=site3)
        iface3 = node3.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface3.set_mode('auto')
        net2.add_interface(iface3)

        # Add NIC to Node1 and add connect to Node3
        node1 = self._slice.get_node(name=node1_name)
        iface4 = node1.add_component(model='NIC_Basic', name='nic2').get_interfaces()[0]
        iface4.set_mode('auto')
        net2.add_interface(iface4)

        # Add a Layer2 Network
        net3 = self._slice.add_l2network(name=network3_name, subnet=IPv4Network("192.168.3.0/24"))

        # Add Node4
        node4 = self._slice.add_node(name=node4_name, site=site1)
        iface5 = node4.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface5.set_mode('auto')
        net3.add_interface(iface5)

        # Add NIC to Node1 and add connect to Node3
        node1 = self._slice.get_node(name=node1_name)
        iface6 = node1.add_component(model='NIC_Basic', name='nic3').get_interfaces()[0]
        iface6.set_mode('auto')
        net3.add_interface(iface6)

        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=4, network_cnt=3)
        node1 = self._slice.get_node(name=node1_name)
        node3 = self._slice.get_node(name=node3_name)
        node4 = self._slice.get_node(name=node4_name)
        self.check_ping(node1=node1, node2=node3, network_name=network2_name)
        self.check_ping(node1=node1, node2=node4, network_name=network3_name)
        # VERIFICATION

        # Removing NIC1 from Node1
        node1 = self._slice.get_node(name=node1_name)
        node1_nic1 = node1.get_component(name="nic1")
        node1_nic1.delete()

        # Removing Node2 from Slice
        node2 = self._slice.get_node(name=node2_name)
        node2.delete()

        # Net1 is a wide area network and no longer have two participants after Node1 being removed
        # Removing the network
        net1 = self._slice.get_network(name=network1_name)
        net1.delete()
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=3, network_cnt=2)
        # VERIFICATION

        self._slice.delete()
