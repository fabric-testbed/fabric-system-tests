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


class FabNetv6ExtSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "FabNetv6Ext"
        super(FabNetv6ExtSliceTest, self).setUp()

    def test_slice(self):
        [site1, site2] = self._fablib.get_random_sites(count=2)
        print(f"Sites: {site1}, {site2}")

        node1_name = 'Node1'
        node2_name = 'Node2'

        network1_name = 'net1'
        network2_name = 'net2'

        node1_nic_name = 'nic1'
        node2_nic_name = 'nic2'

        # External network to connect to
        # Example subnet to Caltech Host is used here
        external_network_subnet = '2605:d9c0:2:10::2:210/64'

        # Node1
        node1 = self._slice.add_node(name=node1_name, site=site1)
        iface1 = node1.add_component(model='NIC_Basic', name=node1_nic_name).get_interfaces()[0]

        # Node2
        node2 = self._slice.add_node(name=node2_name, site=site2)
        iface2 = node2.add_component(model='NIC_Basic', name=node2_nic_name).get_interfaces()[0]

        # NetworkS
        net1 = self._slice.add_l3network(name=network1_name, interfaces=[iface1], type='IPv6Ext')
        net2 = self._slice.add_l3network(name=network2_name, interfaces=[iface2], type='IPv6Ext')

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=2, network_cnt=2)
        # VERIFICATION

        # Manually configure IP addresses
        self._slice.update()
        network1 = self._slice.get_network(name=network1_name)
        network1_available_ips = network1.get_available_ips()
        network1.show()

        network2 = self._slice.get_network(name=network2_name)
        network2_available_ips = network2.get_available_ips()
        network2.show();

        # Enable Public IPv4 make_ip_publicly_routable
        network1.make_ip_publicly_routable(ipv6=[str(network1_available_ips[0])])

        # Enable Public IPv4 make_ip_publicly_routable
        network2.make_ip_publicly_routable(ipv6=[str(network2_available_ips[0])])

        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=2, network_cnt=2)
        # VERIFICATION

        self._slice.update()
        network1 = self._slice.get_network(name=network1_name)
        network2 = self._slice.get_network(name=network2_name)

        # Configure Node1
        node1 = self._slice.get_node(name=node1_name)
        node1_iface = node1.get_interface(network_name=network1_name)
        node1_addr = network1.get_public_ips()[0]
        node1_iface.ip_addr_add(addr=node1_addr, subnet=network1.get_subnet())

        # Add route to external network
        # Please be careful when configuring routes using external network. Do not make these routes default to avoid loosing connections to management network destinations.
        stdout, stderr = node1.execute(
            f'sudo ip route add {external_network_subnet} via {network1.get_gateway()} dev {node1_iface.get_device_name()}')

        self.assertEqual("", stderr, "sudo ip route add failed")

        stdout, stderr = node1.execute(f'sudo ip addr show {node1_iface.get_device_name()}')
        self.assertEqual("", stderr, "sudo ip addr show failed")

        stdout, stderr = node1.execute(f'sudo ip -6 route list')
        self.assertEqual("", stderr, "sudo ip -6 route list failed")

        # Configure Node2
        node2 = self._slice.get_node(name=node2_name)
        node2_iface = node2.get_interface(network_name=network2_name)
        node2_addr = network2.get_public_ips()[0]
        node2_iface.ip_addr_add(addr=node2_addr, subnet=network2.get_subnet())

        # Add route to external network
        stdout, stderr = node2.execute(
            f'sudo ip route add {external_network_subnet} via {network2.get_gateway()} dev {node2_iface.get_device_name()}')
        self.assertEqual("", stderr)

        stdout, stderr = node2.execute(f'sudo ip addr show {node2_iface.get_device_name()}')
        self.assertEqual("", stderr, "sudo ip addr show failed")

        stdout, stderr = node2.execute(f'sudo ip -6 route list')
        self.assertEqual("", stderr, "sudo ip -6 route list failed")

        # VERIFICATION
        # Verify external connectivity
        stdout, stderr = node1.execute(f'sudo ping -c 5 -I {node1_iface.get_device_name()} bing.com')
        self.assertTrue("5 packets transmitted, 5 received" in stdout)
        self.assertEqual("", stderr, "ping failed")

        stdout, stderr = node1.execute(f'sudo ping -c 5 -I {node2_iface.get_device_name()} bing.com')
        self.assertTrue("5 packets transmitted, 5 received" in stdout)
        self.assertEqual("", stderr, "ping failed")
        # VERIFICATION

        self._slice.delete()
