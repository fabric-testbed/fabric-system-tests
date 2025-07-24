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
import pytest
import traceback
import time
from fabrictestbed_extensions.fablib.fablib import FablibManager
from concurrent.futures import ThreadPoolExecutor, as_completed


from tests.utils import error_message, save_results_json, make_site_pairs, wait_and_configure_slices
from tests.base_test import fabric_rc, fim_lock


NIC_MODEL = 'NIC_Basic'
NIC_CAPACITY_FIELD = 'nic_basic_capacity'
NETWORK_TYPE = 'IPv6'
MAX_PARALLEL = 2  # FABNetv6 provisioning can be slow


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_sites_with_workers(fablib) -> list[str]:
    """Return sites with >=1 NIC and workers."""
    result = []
    for site in fablib.list_sites(output="list"):
        if site.get("state") != "Active":
            continue
        if site.get(NIC_CAPACITY_FIELD, 0) < 1:
            continue
        hosts = site.get("hosts", 0)
        if hosts >= 1:
            result.append(site["name"])
    return result


def create_fabnetv6_sharednic_slice(site):
    with fim_lock:
        fablib = FablibManager(fabric_rc=fabric_rc)
        slice_name = f"test-g-324-fabnetv6-{site.lower()}-{int(time.time())}"
        print(f"[{site}] Creating FABNetv6 slice: {slice_name}")

        slice_obj = fablib.new_slice(name=slice_name)

        node1 = slice_obj.add_node(name="node1", site=site)
        iface1 = node1.add_component(model=NIC_MODEL, name="nic1").get_interfaces()[0]
        iface1.set_mode("auto")
        net1 = slice_obj.add_l3network(name="fabnetv6-net1", interfaces=[iface1], type=NETWORK_TYPE)

        slice_obj.submit(wait=False)
        return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"Deletion error: {e}")


def test_fabnetv6_sharednic_ping(fablib):
    results = {}
    slice_objects = {}

    site_names = get_sites_with_workers(fablib)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        future_to_pair = {
            executor.submit(create_fabnetv6_sharednic_slice, site): site
            for site in site_names
        }

        for future in as_completed(future_to_pair):
            site_name = future_to_pair[future]
            try:
                slice_obj = future.result()
                slice_objects[site_name] = slice_obj
            except Exception as e:
                print(f"[{site_name}] Slice creation failed: {e}")
                traceback.print_exc()
                results[site_name] = {
                    "state": False,
                    "error": error_message(slice_obj=slice_obj, exception=e)
                }

    wait_and_configure_slices(slice_objects)
    for site_name, slice_obj in slice_objects.items():
        try:
            slice_obj.post_boot_config()

            node1 = slice_obj.get_node("node1")
            net1 = slice_obj.get_network("fabnetv6-net1")

            node1.ip_route_add(
                    subnet=fablib.FABNETV4_SUBNET,
                    gateway=net1.get_gateway(),
            )

            results[site_name] = {
                "state": True,
                "error": ""
            }
        except Exception as e:
            print(f"[{site_name}] FABNetv6 ping test failed: {e}")
            traceback.print_exc()
            results[site_name] = {
                "state": False,
                "error": error_message(slice_obj=slice_obj, exception=e)
            }

    slices_to_keep = []
    ping_results = {}
    site_pairs = make_site_pairs(site_names)
    for src, dst in site_pairs:
        if src == dst:
            continue  # Skip same-slice tests
        pair_key = f"{src}->{dst}"
        print(f"Testing {pair_key}...")

        try:
            slice_objects[src].post_boot_config()
            slice_objects[dst].post_boot_config()

            src_node = slice_objects[src].get_node("node1")
            dst_node = slice_objects[dst].get_node("node1")
            dst_iface = dst_node.get_interface(network_name="fabnetv6-net1")
            dst_ip = dst_iface.get_ip_addr()

            ping_out, _ = src_node.execute(f"ping6 -c 5 {dst_ip}")
            if "0% packet loss" in ping_out:
                pair_result = {"state": True,
                               "error": ""}
            else:
                pair_result = {"state": False,
                               "error": "Ping Failed"}
                slices_to_keep.append(src)
                slices_to_keep.append(dst)

            ping_results[pair_key] = pair_result
        except Exception as e:
            print(f"[{pair_key}] FabNetv6 Ping test failed: {e}")
            traceback.print_exc()
            ping_results[pair_key] = {
                "state": False,
                "error": error_message(slice_obj=slice_obj, exception=e)
            }

    print("TEST SUMMARY==========================================================================================")
    # Cleanup only successful slices
    for site_name, slice_obj in slice_objects.items():
        site_info = results.get(site_name, {})
        if site_info.get("state", False):
            print(f"{site_name}: Create PASS")
            if site_name in slice_objects:
                continue
            delete_slice(slice_obj)
        else:
            print(f"{site_name}: {site_info.get('error')}")
            print(f"[{site_name}] Skipping deletion because slice failed. Please inspect manually.")

    for key, info in ping_results.items():
        print(f"{key}: {info}")

    save_results_json(results, filename="fabnetv6_shared.json")
    save_results_json(ping_results, filename="fabnetv6_shared_ping.json")
    print("TEST SUMMARY==========================================================================================")

    #failed = [f"{site}: {info['error']}" for site, info in results.items() if not info["state"]]
    failed = [site for site, info in results.items() if not info["state"]]
    assert not failed, f"FABNetv6 Shared NIC test failed on: {', '.join(failed)}"
