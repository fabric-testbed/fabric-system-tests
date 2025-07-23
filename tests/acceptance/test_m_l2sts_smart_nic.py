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
from fabrictestbed_extensions.fablib.fablib import FablibManager
from concurrent.futures import ThreadPoolExecutor, as_completed
from ipaddress import IPv4Network

from tests.acceptance.utils import error_message
from tests.base_test import fabric_rc, fim_lock


NIC_MODEL = 'NIC_ConnectX_5'
NIC_CAPACITY_FIELD = 'nic_connectx_5_capacity'
NETWORK_NAME = 'l2-STS'
SUBNET = IPv4Network("192.168.1.0/24")
MAX_PARALLEL = 2


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_sites_with_smartnic(fablib):
    """Return sites with >=2 workers and Smart NIC capacity."""
    result = []
    for site in fablib.list_sites(output="list"):
        if site.get("state") != "Active":
            continue
        if site.get(NIC_CAPACITY_FIELD, 0) < 2:
            continue
        result.append(site["name"])
    return result


def make_site_pairs(site_list):
    """
    Return unique non-overlapping (site1_name, site2_name) pairs from site_list.
    Each site appears at most once across all pairs.
    """
    site_names = [site["name"] for site in site_list]
    num_pairs = len(site_names) // 2
    return [(site_names[i], site_names[i + 1]) for i in range(0, 2 * num_pairs, 2)]


def create_l2sts_smartnic_slice(site1, site2):
    with fim_lock:

        fablib = FablibManager(fabric_rc=fabric_rc)

        slice_name = f"test-m-323-l2sts-smartnic-{site1.lower()}-{site2.lower()}-{int(time.time())}"
        print(f"[{site1}/{site2}] Creating L2STS SmartNIC slice: {slice_name}")

        slice_obj = fablib.new_slice(name=slice_name)

        node1 = slice_obj.add_node(name="node1", site=site1)
        iface1 = node1.add_component(model=NIC_MODEL, name="nic1").get_interfaces()[0]
        iface1.set_mode("auto")

        node2 = slice_obj.add_node(name="node2", site=site2)
        iface2 = node2.add_component(model=NIC_MODEL, name="nic2").get_interfaces()[0]
        iface2.set_mode("auto")

        node3 = slice_obj.add_node(name="node3", site=site2)
        iface3 = node3.add_component(model=NIC_MODEL, name="nic3").get_interfaces()[0]
        iface3.set_mode("auto")

        slice_obj.add_l2network(name=NETWORK_NAME, interfaces=[iface1, iface2, iface3], type='L2STS', subnet=SUBNET)
        slice_obj.submit(wait=False)
        return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"Deletion error: {e}")


def test_l2sts_smartnic_ping(fablib):
    results = {}
    slice_objects = {}

    sites_with_workers = get_sites_with_smartnic(fablib)
    site_pairs = make_site_pairs(sites_with_workers)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        future_to_triplet = {
            executor.submit(create_l2sts_smartnic_slice, site1, site2): (site1, site2)
            for site1, site2, in site_pairs
        }

        for future in as_completed(future_to_triplet):
            site1, site2 = future_to_triplet[future]
            key = f"{site1}-{site2}"
            try:
                slice_obj = future.result()
                slice_objects[key] = slice_obj
            except Exception as e:
                print(f"[{key}] Slice creation failed: {e}")
                traceback.print_exc()
                results[key] = {
                    "state": False,
                    "error": error_message(slice_obj=slice_obj, exception=e)
                }

    for key, slice_obj in slice_objects.items():
        try:
            slice_obj.wait(progress=False)
            slice_obj.wait_ssh(progress=False)
            slice_obj.post_boot_config()

            node1 = slice_obj.get_node("node1")
            node2 = slice_obj.get_node("node2")
            node3 = slice_obj.get_node("node3")

            iface1 = node1.get_interface(network_name=NETWORK_NAME)
            iface2 = node2.get_interface(network_name=NETWORK_NAME)
            iface3 = node3.get_interface(network_name=NETWORK_NAME)

            ip1 = iface1.get_ip_addr()
            ip2 = iface2.get_ip_addr()
            ip3 = iface3.get_ip_addr()

            iface1.ip_addr_add(addr=ip1, subnet=SUBNET)
            iface2.ip_addr_add(addr=ip2, subnet=SUBNET)
            iface3.ip_addr_add(addr=ip3, subnet=SUBNET)

            node1.execute(f"ip addr show {iface1.get_os_interface()}")
            node2.execute(f"ip addr show {iface2.get_os_interface()}")
            node3.execute(f"ip addr show {iface3.get_os_interface()}")

            stdout, _ = node1.execute(f"ping -c 5 {ip2}")
            assert "0% packet loss" in stdout, f"[{key}] Ping failed"
            stdout, _ = node1.execute(f"ping -c 5 {ip3}")
            assert "0% packet loss" in stdout, f"[{key}] Ping failed"
            stdout, _ = node2.execute(f"ping -c 5 {ip3}")
            assert "0% packet loss" in stdout, f"[{key}] Ping failed"

            results[key] = {
                "state": True,
                "error": ""
            }
        except Exception as e:
            print(f"[{key}] L2STS SmartNIC test failed: {e}")
            traceback.print_exc()
            results[key] = {
                "state": False,
                "error": error_message(slice_obj=slice_obj, exception=e)
            }

    # Cleanup only successful slices
    for site_name, slice_obj in slice_objects.items():
        if results.get(site_name, {}).get("state", False):
            delete_slice(slice_obj)
        else:
            print(f"[{site_name}] Skipping deletion because slice failed. Please inspect manually.")

    failed = [f"{site}: {info['error']}" for site, info in results.items() if not info["state"]]
    assert not failed, f"L2STS SmartNIC test failed on: {', '.join(failed)}"
