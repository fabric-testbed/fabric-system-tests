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
from ipaddress import IPv4Network

from tests.utils import error_message, save_results_json, make_site_pairs
from tests.base_test import fabric_rc, fim_lock


VM_CONFIG = {"cores": 10, "ram": 20, "disk": 50}
NIC_MODELS = {
    'NIC_ConnectX_5': 'nic_connectx_5_capacity',
    'NIC_ConnectX_6': 'nic_connectx_6_capacity'
}
NETWORK_NAME = 'l2-PTP'
SUBNET = IPv4Network("192.168.1.0/24")
MAX_PARALLEL_TESTS = 3


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_smartnic_sites(fablib, nic_capacity_field):
    return [
        site for site in fablib.list_sites(output="list")
        if site.get("state") == "Active" and site.get(nic_capacity_field, 0) >= 1
    ]


def create_l2ptp_slice(site1, site2, nic_model):
    with fim_lock:

        fablib = FablibManager(fabric_rc=fabric_rc)

        slice_name = f"test-k-322-l2ptp-{nic_model.lower()}-{site1.lower()}-{site2.lower()}-{int(time.time())}"
        print(f"[{site1}/{site2}] Creating L2PTP slice with {nic_model}: {slice_name}")

        slice_obj = fablib.new_slice(name=slice_name)

        node1 = slice_obj.add_node(name="node1", site=site1,
                                   cores=VM_CONFIG["cores"], ram=VM_CONFIG["ram"], disk=VM_CONFIG["disk"])
        iface1 = node1.add_component(model=nic_model, name="nic1").get_interfaces()[0]
        iface1.set_mode("auto")

        node2 = slice_obj.add_node(name="node2", site=site2,
                                   cores=VM_CONFIG["cores"], ram=VM_CONFIG["ram"], disk=VM_CONFIG["disk"])
        iface2 = node2.add_component(model=nic_model, name="nic2").get_interfaces()[0]
        iface2.set_mode("auto")

        slice_obj.add_l2network(name=NETWORK_NAME, interfaces=[iface1, iface2], type='L2PTP', subnet=SUBNET)
        slice_obj.submit(wait=False)
        return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"[{slice_obj.get_name()}] Slice deletion error: {e}")


def test_smartnic_l2ptp_across_sites(fablib):
    results = {}
    slice_objects = {}

    test_tasks = []

    for nic_model, capacity_field in NIC_MODELS.items():
        sites = get_smartnic_sites(fablib, capacity_field)
        if len(sites) < 2:
            print(f"Skipping {nic_model}: Not enough sites with {capacity_field}")
            continue
        site_names = [site["name"] for site in sites]
        site_pairs = make_site_pairs(site_names)
        for site1, site2 in site_pairs:
            test_tasks.append((site1, site2, nic_model))

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_TESTS) as executor:
        future_to_pair = {
            executor.submit(create_l2ptp_slice, site1, site2, nic_model): (site1, site2, nic_model)
            for (site1, site2, nic_model) in test_tasks
        }

        for future in as_completed(future_to_pair):
            site1, site2, nic_model = future_to_pair[future]
            key = f"{site1}-{site2}-{nic_model}"
            try:
                slice_obj = future.result()
                slice_objects[key] = slice_obj
            except Exception as e:
                print(f"[{key}] Slice submission failed: {e}")
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

            iface1 = node1.get_interface(network_name=NETWORK_NAME)
            ip1 = iface1.get_ip_addr()

            iface2 = node2.get_interface(network_name=NETWORK_NAME)
            ip2 = iface2.get_ip_addr()

            stdout, _ = node1.execute(f"ping -c 5 {ip2}")
            if "0% packet loss" not in stdout:
                raise Exception(f"[{key}] Ping failed")

            results[key] = {
                "state": True,
                "error": ""
            }

        except Exception as e:
            print(f"[{key}] L2PTP reachability test failed: {e}")
            traceback.print_exc()
            results[key] = {
                "state": False,
                "error": error_message(slice_obj=slice_obj, exception=e)
            }

    print("TEST SUMMARY==========================================================================================")
    # Cleanup only successful slices
    for site_name, slice_obj in slice_objects.items():
        site_info = results.get(site_name, {})
        if site_info.get("state", False):
            print(f"{site_name}: PASS")
            delete_slice(slice_obj)
        else:
            print(f"{site_name}: {site_info.get('error')}")
            print(f"[{site_name}] Skipping deletion because slice failed. Please inspect manually.")

    save_results_json(results, filename="l2ptp_smart_nic.json")
    print("TEST SUMMARY==========================================================================================")

    #failed = [f"{site}: {info['error']}" for site, info in results.items() if not info["state"]]
    failed = [site for site, info in results.items() if not info["state"]]
    assert not failed, f"L2PTP SmartNIC tests failed on: {', '.join(failed)}"
