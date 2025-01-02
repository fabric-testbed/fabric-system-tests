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
from datetime import datetime
from tests.base_test import BaseTest


class FabNetv4ExtRenewSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "FabNetv4ExtRenew"
        super(FabNetv4ExtRenewSliceTest, self).setUp()

    def test_slice(self):
        [site1, site2] = self._fablib.get_random_sites(count=2)
        print(f"Sites: {site1}, {site2}")

        node1_name = 'Node1'
        node2_name = 'Node2'

        network1_name = 'net1'
        network2_name = 'net2'

        node1_nic_name = 'nic1'
        node2_nic_name = 'nic2'

        # Node1
        node1 = self._slice.add_node(name=node1_name, site=site1)
        iface1 = node1.add_component(model='NIC_Basic', name=node1_nic_name).get_interfaces()[0]

        # Node2
        node2 = self._slice.add_node(name=node2_name, site=site2)
        iface2 = node2.add_component(model='NIC_Basic', name=node2_nic_name).get_interfaces()[0]

        # NetworkS
        net1 = self._slice.add_l3network(name=network1_name, interfaces=[iface1], type='IPv4Ext')
        net2 = self._slice.add_l3network(name=network2_name, interfaces=[iface2], type='IPv4Ext')

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
        network1.make_ip_publicly_routable(ipv4=[str(network1_available_ips[0])])

        # Enable Public IPv4 make_ip_publicly_routable
        network2.make_ip_publicly_routable(ipv4=[str(network2_available_ips[0])])

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

        # Add route to external network Google DNS server in this case
        stdout, stderr = node1.execute(f'sudo ip route add 8.8.8.0/24 via {network1.get_gateway()}')
        self.assertEqual("", stderr)

        stdout, stderr = node1.execute(f'ip addr show {node1_iface.get_device_name()}')
        self.assertEqual("", stderr)

        stdout, stderr = node1.execute(f'ip route list')
        self.assertEqual("", stderr)

        # Configure Node2
        node2 = self._slice.get_node(name=node2_name)
        node2_iface = node2.get_interface(network_name=network2_name)
        node2_addr = network2.get_public_ips()[0]
        node2_iface.ip_addr_add(addr=node2_addr, subnet=network2.get_subnet())

        # Add route to external network Google DNS server in this case
        stdout, stderr = node2.execute(f'sudo ip route add 8.8.8.0/24 via {network2.get_gateway()}')
        self.assertEqual("", stderr)

        stdout, stderr = node2.execute(f'ip addr show {node2_iface.get_device_name()}')
        self.assertEqual("", stderr)

        stdout, stderr = node2.execute(f'ip route list')
        self.assertEqual("", stderr)

        # VERIFICATION
        # Ping Google's DNS server from Node1 via the FabNetv4Ext network
        stdout, stderr = node1.execute(
            f"sudo ping -c 5 8.8.8.8 -I {node1.get_interface(network_name=network1_name).get_device_name()}")
        self.assertTrue("5 packets transmitted, 5 received" in stdout)
        self.assertEqual("", stderr)

        # Ping Google's DNS server from Node2 via the FabNetv4Ext network
        stdout, stderr = node2.execute(
            f"sudo ping -c 5 8.8.8.8 -I {node2.get_interface(network_name=network2_name).get_device_name()}")
        print(stdout)
        print(stderr)
        self.assertTrue("5 packets transmitted, 5 received" in stdout)
        self.assertEqual("", stderr)
        # VERIFICATION

        # Renew slice
        current_lease_end = datetime.strptime(self._slice.get_lease_end(), "%Y-%m-%d %H:%M:%S %z")
        self._slice.renew(days=3)

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=2, network_cnt=2)
        new_lease_end = datetime.strptime(self._slice.get_lease_end(), "%Y-%m-%d %H:%M:%S %z")
        self.assertTrue(new_lease_end > current_lease_end)
        # VERIFICATION

        self._slice.delete()
