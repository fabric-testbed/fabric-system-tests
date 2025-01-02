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


class FpgaSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "Fpga"
        super(FpgaSliceTest, self).setUp()

    def test_slice(self):
        FPGA_CHOICE = 'FPGA_Xilinx_U280'

        # don't edit - convert from FPGA type to a resource column name
        # to use in filter lambda function below
        choice_to_column = {
            "FPGA_Xilinx_U280": "fpga_u280_available",
        }

        column_name = choice_to_column.get(FPGA_CHOICE, "Unknown")
        print(f'{column_name=}')

        import random

        # you can limit to one of the sites on this list (or use None)
        # allowed_sites = ['MAX', 'INDI']
        allowed_sites = None

        fpga_sites_df = self._fablib.list_sites(output='pandas', quiet=True, filter_function=lambda x: x[column_name] > 0)
        # note that list_sites with 'pandas' doesn't actually return a dataframe like doc sez, it returns a Styler
        # based on the dataframe
        fpga_sites = fpga_sites_df.data['Name'].values.tolist()
        print(f'All sites with FPGA available: {fpga_sites}')

        self.assertNotEqual(0, len(fpga_sites), 'Warning - no sites with available FPGAs found')
        site = random.choice(fpga_sites)
        node_name = 'fpga-node'

        # Add node with a 100G drive and a couple of CPU cores (default)
        node = self._slice.add_node(name=node_name, site=site, disk=100)
        node.add_component(model=FPGA_CHOICE, name='fpga1')

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=1, network_cnt=0)

        node = self._slice.get_node(node_name)

        command = "sudo dnf install -q -y pciutils usbutils"
        stdout, stderr = node.execute(command)

        print('Checking to see if Xilinx PCI device(s) are present')
        command = "lspci | grep 'Xilinx'"
        stdout, stderr = node.execute(command)
        self.assertEqual("", stderr, "lspci failed")
        self.assertNotEqual("", stdout, "Xilinx device not found")

        print('Checking to see if JTAG-over-USB is available')
        command = "lsusb -d 0403:6011"
        stdout, stderr = node.execute(command)
        self.assertEqual("", stderr, "lsusb failed")
        self.assertNotEqual("", stdout, "usb tag device not found")
        # VERIFICATION

        self._slice.delete()
