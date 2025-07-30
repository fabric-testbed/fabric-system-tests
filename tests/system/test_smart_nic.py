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


class SmartNicSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "SmartNIc"
        super(SmartNicSliceTest, self).setUp()

    def test_slice(self):
        site = self._fablib.get_random_site(filter_function=lambda x: x['nic_connectx_5_available'] > 0)
        print(f"site: {site}")

        node_name = 'Node1'

        # Add node
        node = self._slice.add_node(name=node_name, site=site)

        # Add an NVME Drive
        node.add_component(model='NIC_Basic', name='nic1')
        node.add_component(model='NIC_ConnectX_6', name='nic2')

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=1, network_cnt=0)

        node = self._slice.get_node(node_name)

        # VERIFICATION
        node.execute("sudo dnf install -y pciutils")
        cmd = "sudo dnf install -y -q pciutils && lspci | grep -i ConnectX"
        stdout, stderr = node.execute(cmd)

        if "ConnectX-6" not in stdout or "ConnectX-5" not in stdout:
            raise Exception(f"Smart NIC not detected in lspci")

        # Should see 4 entries: 2 cards × 2 ports
        nic_count = stdout.count("Ethernet controller: Mellanox Technologies")
        if nic_count < 2:
            raise Exception(f"Expected >=2 NIC entries, found {nic_count}")

        self._slice.delete()
