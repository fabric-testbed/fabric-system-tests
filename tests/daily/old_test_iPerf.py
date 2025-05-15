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
from fim.user import Labels, Capacities

from tests.base_test import BaseTest
from tests.daily.slice_helper_old import SliceHelper


class iPerfTest(BaseTest):
    def setUp(self):
        self.prefix = "iPerf"
        self.wait = False
        self.skip_hosts = []
        self.docker_image = 'pruth/fabric-multitool-rockylinux9:latest'
        super(iPerfTest, self).setUp()
        self._fablib.delete_all()

    def test_iperf3(self):
        site_count = 2
        avoid = ["UKY"]
        if "orchestrator" in self._fablib.get_orchestrator_host():
            site_count = 30
            avoid = ["EDUKY"]
        sites = self._fablib.get_random_sites(count=site_count, avoid=avoid)
        #sites = self._fablib.get_site_names()
        sites.sort()
        print(f"Sites: {sites}")

        slice_helper = SliceHelper(fablib_mgr=self._fablib,
                                   slice_name_prefix=self.prefix,
                                   sites=sites,
                                   skip_hosts=self.skip_hosts,
                                   docker_image=self.docker_image,
                                   wait=False)

        self.assertTrue(slice_helper.run(run_iperf=True))
