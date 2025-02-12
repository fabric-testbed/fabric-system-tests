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
import os
import socket
import time
from ipaddress import IPv4Network, IPv4Address

from tests.base_test import BaseTest
from fabrictestbed_extensions.fablib.fablib import FablibManager as fablib_manager


class P4SwitchSliceTest:
    def __init__(self):
        self.prefix = "P4Switch"
        time_stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        host = socket.gethostname()
        slice_name = f"ST-Slice-{self.prefix}-{time_stamp}-{host}"
        fabric_rc_location = os.getenv("FABRIC_RC_LOCATION")
        self._fablib = fablib_manager(fabric_rc=fabric_rc_location)
        self._slice = self._fablib.new_slice(name=slice_name)

        #super(P4SwitchSliceTest, self).setUp()

    def p4_slice(self):
        p4_column_name = 'p4-switch_available'

        # Find a site which has a P4 Switch available
        [site2] = self._fablib.get_random_sites(count=1, filter_function=lambda x: x[p4_column_name] > 0)

        # Choose another random site other than P4 site to host the VMs
        site1 = self._fablib.get_random_site(avoid=[site2])

        print(f"Sites chosen for hosting VMs: {site1} P4: {site2}")

        node1_name = 'Node1'
        node2_name = 'Node2'
        network1_name = 'net1'
        network2_name = 'net2'
        p4_name = 'P4'

        # Network
        net1 = self._slice.add_l2network(name=network1_name, subnet=IPv4Network("192.168.0.0/24"))
        net2 = self._slice.add_l2network(name=network2_name, subnet=IPv4Network("192.168.0.0/24"))

        # Node1
        node1 = self._slice.add_node(name=node1_name, site=site1)
        iface1 = node1.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface1.set_mode('config')
        net1.add_interface(iface1)
        iface1.set_ip_addr(IPv4Address("192.168.0.1"))

        # Create P4 switch and its links
        p4 = self._slice.add_switch(name=p4_name, site=site2)
        iface2 = p4.get_interfaces()[0]
        iface3 = p4.get_interfaces()[1]

        net1.add_interface(iface2)
        net2.add_interface(iface3)

        # Node2
        node2 = self._slice.add_node(name=node2_name, site=site2)
        iface4 = node2.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface4.set_mode('auto')
        net2.add_interface(iface4)
        iface4.set_ip_addr(IPv4Address("192.168.0.2"))

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=3, network_cnt=2)
        # VERIFICATION

        #self._slice.delete()


if __name__ == '__main__':
    obj = P4SwitchSliceTest()
    obj.p4_slice()
