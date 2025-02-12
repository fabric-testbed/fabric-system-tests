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


class PersistentStorageSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "PersistentStorage"
        super(PersistentStorageSliceTest, self).setUp()

    def test_slice(self):
        site = 'EDC'
        storage_name = f'acceptance-testing'

        # Add a node
        node = self._slice.add_node(name="Node1", site=site)
        node.add_storage(name=storage_name)

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=1, network_cnt=0)

        node = self._slice.get_node('Node1')

        storage = node.get_storage(storage_name)

        print(f"Storage Device Name: {storage.get_device_name()}")
        self.assertIsNotNone(storage.get_device_name(), "Storage device name not found")
        self.assertNotEqual("", storage.get_device_name(), "Storage device name not found")

        #stdout, stderr = node.execute(f"sudo mkfs.ext4 {storage.get_device_name()}")
        #self.assertEqual("", stderr, "Filesystem install on storage failed")

        stdout, stderr = node.execute(f"sudo mkdir /mnt/fabric_storage; "
                                      f"sudo mount {storage.get_device_name()} /mnt/fabric_storage; "
                                      f"df -h")
        self.assertEqual("", stderr, "Mound failed")
        # VERIFICATION

        self._slice.delete()
