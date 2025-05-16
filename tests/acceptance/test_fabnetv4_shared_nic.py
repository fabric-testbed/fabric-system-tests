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
from itertools import combinations

import pytest
import traceback
import time
from ipaddress import IPv4Network
from fabrictestbed_extensions.fablib.fablib import FablibManager
from concurrent.futures import ThreadPoolExecutor, as_completed
from tests.base_test import fabric_rc, fim_lock


NIC_MODEL = 'NIC_Basic'
NIC_CAPACITY_FIELD = 'nic_basic_capacity'
NETWORK_TYPE = 'IPv4'
MAX_PARALLEL = 2  # FABNetv4 provisioning can be slow
SUBNET = IPv4Network("192.168.100.0/24")


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_sites_with_workers(fablib):
    """Return sites with >=1 NIC and workers."""
    result = []
    for site in fablib.list_sites(output="list"):
        if site.get("state") != "Active":
            continue
        if site.get(NIC_CAPACITY_FIELD, 0) < 1:
            continue
        workers = site.get("hosts", [])
        if len(workers) >= 1:
            result.append((site["name"], sorted(workers)))
    return result


def make_site_pairs(sites):
    """
    Return unique (site1, site2, worker1, worker2) pairs where each site has at least one worker.
    Avoids (a, a) and symmetric duplicates (a, b) / (b, a).
    """
    pairs = []
    for (site1, workers1), (site2, workers2) in combinations(sites, 2):
        if workers1 and workers2:
            pairs.append((site1, site2, workers1[0], workers2[0]))
    return pairs


def create_fabnetv4_sharednic_slice(site1, site2, w1, w2):
    with fim_lock:
        fablib = FablibManager(fabric_rc=fabric_rc)
        slice_name = f"test-324-fabnetv4-{site1.lower()}-{site2.lower()}-{int(time.time())}"
        print(f"[{site1}/{site2}] Creating FABNetv4 slice: {slice_name}")

        slice_obj = fablib.new_slice(name=slice_name)

        node1 = slice_obj.add_node(name="node1", site=site1, host=w1)
        iface1 = node1.add_component(model=NIC_MODEL, name="nic1").get_interfaces()[0]

        node2 = slice_obj.add_node(name="node2", site=site2, host=w2)
        iface2 = node2.add_component(model=NIC_MODEL, name="nic2").get_interfaces()[0]

        net1 = slice_obj.add_l3network(name="fabnetv4-net1", interfaces=[iface1], type=NETWORK_TYPE)
        net2 = slice_obj.add_l3network(name="fabnetv4-net2", interfaces=[iface2], type=NETWORK_TYPE)

        slice_obj.submit(wait=False)
        return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"Deletion error: {e}")


def test_fabnetv4_sharednic_ping(fablib):
    results = {}
    slice_objects = {}
    available_ips = list(SUBNET)[1:]

    site_pairs = make_site_pairs(get_sites_with_workers(fablib))

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        future_to_pair = {
            executor.submit(create_fabnetv4_sharednic_slice, site1, site2, w1, w2): (site1, site2)
            for site1, site2, w1, w2 in site_pairs
        }

        for future in as_completed(future_to_pair):
            site1, site2 = future_to_pair[future]
            key = f"{site1}-{site2}"
            try:
                slice_obj = future.result()
                slice_objects[key] = slice_obj
            except Exception as e:
                print(f"[{key}] Slice creation failed: {e}")
                traceback.print_exc()
                results[key] = False

    for key, slice_obj in slice_objects.items():
        try:
            slice_obj.wait(progress=False)
            slice_obj.wait_ssh(progress=False)
            slice_obj.post_boot_config()

            node1 = slice_obj.get_node("node1")
            node2 = slice_obj.get_node("node2")

            iface1 = node1.get_interface(network_name="fabnetv4-net1")
            iface2 = node2.get_interface(network_name="fabnetv4-net2")

            ip1 = str(available_ips.pop(0))
            ip2 = str(available_ips.pop(0))

            iface1.ip_addr_add(addr=ip1, subnet=SUBNET)
            iface2.ip_addr_add(addr=ip2, subnet=SUBNET)

            node1.ip_route_add(subnet=SUBNET, gateway=None)
            node2.ip_route_add(subnet=SUBNET, gateway=None)

            node1.execute(f"ip addr show {iface1.get_os_interface()}")
            node2.execute(f"ip addr show {iface2.get_os_interface()}")

            node1.execute(f"ping -c 5 {ip2}")
            node2.execute(f"ping -c 5 {ip1}")

            results[key] = True
        except Exception as e:
            print(f"[{key}] FABNetv4 ping test failed: {e}")
            traceback.print_exc()
            results[key] = False

    for slice_obj in slice_objects.values():
        delete_slice(slice_obj)

    failed = [k for k, passed in results.items() if not passed]
    assert not failed, f"FABNetv4 Shared NIC test failed on: {', '.join(failed)}"
