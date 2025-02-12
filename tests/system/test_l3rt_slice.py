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
from tests.base_test import BaseTest


class L3rtSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "L3RT"
        super(L3rtSliceTest, self).setUp()

    def test_slice(self):
        [site1, site2] = self._fablib.get_random_sites(count=2)
        print(f"Sites: {site1}, {site2}")

        node1_name = 'Node1'
        node2_name = 'Node2'

        network1_name = 'net1'
        network2_name = 'net2'
        network3_name = 'net3'
        network4_name = 'net4'

        # Networks
        net1 = self._slice.add_l3network(name=network1_name, type='IPv4')
        net2 = self._slice.add_l3network(name=network2_name, type='IPv4')
        net3 = self._slice.add_l3network(name=network3_name, type='IPv6')
        net4 = self._slice.add_l3network(name=network4_name, type='IPv6')

        # Node1
        node1 = self._slice.add_node(name=node1_name, site=site1)
        iface1 = node1.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface1.set_mode('auto')
        net1.add_interface(iface1)
        node1.add_route(subnet=self._fablib.FABNETV4_SUBNET, next_hop=net1.get_gateway())

        iface3 = node1.add_component(model='NIC_Basic', name='nic2').get_interfaces()[0]
        iface3.set_mode('auto')
        net3.add_interface(iface3)
        node1.add_route(subnet=self._fablib.FABNETV6_SUBNET, next_hop=net3.get_gateway())

        # Node2
        node2 = self._slice.add_node(name=node2_name, site=site2)
        iface2 = node2.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface2.set_mode('auto')
        net2.add_interface(iface2)
        node2.add_route(subnet=self._fablib.FABNETV4_SUBNET, next_hop=net2.get_gateway())

        iface4 = node2.add_component(model='NIC_Basic', name='nic2').get_interfaces()[0]
        iface4.set_mode('auto')
        net4.add_interface(iface4)
        node2.add_route(subnet=self._fablib.FABNETV6_SUBNET, next_hop=net4.get_gateway())

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=2, network_cnt=4)
        self.check_ping(node1=node1, node2=node2, network_name=network2_name)
        self.check_ping(node1=node1, node2=node2, network_name=network4_name)

        '''
        stdout, stderr = node1.execute("sudo ping -c 5 10.128.0.1")
        self.assertTrue("5 packets transmitted, 5 received" in stdout)
        self.assertEqual("", stderr, "ping failed")

        stdout, stderr = node1.execute("sudo ping -c 5 2602:FCFB:00::1")
        self.assertTrue("5 packets transmitted, 5 received" in stdout)
        self.assertEqual("", stderr, "ping failed")

        stdout, stderr = node2.execute("sudo ping -c 5 10.128.0.1")
        self.assertTrue("5 packets transmitted, 5 received" in stdout)
        self.assertEqual("", stderr, "ping failed")

        stdout, stderr = node2.execute("sudo ping -c 2602:FCFB:00::1")
        self.assertTrue("5 packets transmitted, 5 received" in stdout)
        self.assertEqual("", stderr, "ping failed")
        '''
        # VERIFICATION
        self._slice.delete()
