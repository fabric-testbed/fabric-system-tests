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
import ipaddress
import socket
import time
import unittest

from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager
from fabrictestbed_extensions.fablib.node import Node


class BaseTest(unittest.TestCase):
    def setUp(self):
        time_stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        host = socket.gethostname()
        slice_name = f"ST-Slice-{self.prefix}-{time_stamp}-{host}"
        self._fablib = fablib_manager()
        self._slice = self._fablib.new_slice(name=slice_name)

    def check_slice(self, node_cnt: int = 0, network_cnt: int = 0):
        self.assertIsNotNone(self._slice)
        self._slice.update()
        for n in self._slice.get_nodes():
            print(n)
        self.assertEqual("StableOK", self._slice.get_state(), "Slice is not Stable")
        self.assertEqual(node_cnt, len(self._slice.get_nodes()), "Node count doesn't match")
        self.assertEqual(network_cnt, len(self._slice.get_networks()), "Network count doesn't match")

        for node in self._slice.get_nodes():
            self.assertEqual("Active", node.get_reservation_state())
            self.assertEqual("", node.get_error_message(), "Node provisioning error")
            self.assertIsNotNone(node.get_management_ip(), "None management IP")
            self.assertNotEqual("", node.get_management_ip(), "Empty management IP")

        for network in self._slice.get_networks():
            self.assertEqual("Active", network.get_reservation_state())
            if network.get_type() in ["FABNetv4", "FABNetv4Ext", "FABNetv6", "FABNetv6Ext"]:
                subnet = network.get_subnet()
                self.assertTrue(isinstance(subnet, ipaddress.IPv4Network) or isinstance(subnet, ipaddress.IPv6Network),
                                "Subnet not assigned for FabNet*")
                gateway = network.get_gateway()
                self.assertTrue(
                    isinstance(gateway, ipaddress.IPv4Address) or isinstance(gateway, ipaddress.IPv6Address),
                    "Gateway not assigned for FabNet*")

    def check_ping(self, node1: Node, node2: Node, network_name: str):
        self.assertIsNotNone(node1)
        self.assertIsNotNone(node2)
        node1 = self._slice.get_node(node1.get_name())
        node2 = self._slice.get_node(node2.get_name())
        node2_address = node2.get_interface(network_name=network_name).get_ip_addr()
        self.assertIsNotNone(node2_address)
        stdout, stderr = node1.execute(f'ping -c 5 {node2_address}')
        self.assertTrue("5 packets transmitted, 5 received" in stdout, "ping failed")
        self.assertEqual("", stderr, "ping failed")
