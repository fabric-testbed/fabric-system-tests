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


class AL2SSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "AL2S"
        super(AL2SSliceTest, self).setUp()

    def test_slice(self):
        [site1] = self._fablib.get_random_sites(count=1)
        print(f"Sites: {site1}")

        al2s_network_name = "al2s-net"
        aux_name = al2s_network_name + "_aux"

        # Create a Cloud Facility Port
        fabric_facility_port = self._slice.add_facility_port(name='Cloud-Facility-AWS', site='AWS',
                                                             # Only specify device name
                                                             labels=Labels(ipv4_subnet='192.168.30.1/24',
                                                                           device_name='agg3.dall3'),
                                                             # Peer Labels
                                                             peer_labels=Labels(ipv4_subnet='192.168.30.2/24',
                                                                                asn='64512',
                                                                                bgp_key='0xzsEwC7xk6c1fK_h.xHyAdx',
                                                                                account_id='296256999979',
                                                                                local_name="AWS"),
                                                             # MTU must be set to 9001 for Cloud Facility Ports
                                                             bandwidth=50, mtu=9000)

        fabric_facility_port_iface = fabric_facility_port.get_interfaces()[0]

        # Create Cloud L3VPN and connect to Cloud Facility Port
        al2s = self._slice.add_l3network(name=al2s_network_name, interfaces=[fabric_facility_port_iface], type='L3VPN',
                                         technology='AL2S')

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=0, network_cnt=1)
        # VERIFICATION

        net1 = self._slice.get_network(al2s_network_name)

        aux_net = self._slice.add_l3network(name=aux_name, type='L3VPN')
        node1 = self._slice.add_node(name="anode", site=site1)
        iface1 = node1.add_component(model='NIC_Basic', name='nic1').get_interfaces()[0]
        iface1.set_mode('manual')
        iface1.set_subnet(ipv4_subnet='192.168.10.1/24')

        aux_net.add_interface(iface1)
        net1.peer(aux_net,
                  labels=Labels(bgp_key='secret', ipv4_subnet='192.168.50.1/24'),
                  capacities=Capacities(mtu=9000),
                  peer_labels=Labels(local_name="FABRIC"))

        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=1, network_cnt=2)
        # VERIFICATION

        self._slice.list_nodes()
        self._slice.list_networks()
        self._slice.list_interfaces()

        self._slice.delete()
