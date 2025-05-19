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
from tests.base_test import fabric_rc, fim_lock


NIC_MODEL = 'NIC_Basic'
VM_CONFIG = {"cores": 10, "ram": 20, "disk": 50}
MAX_PARALLEL_SITES = 5


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_active_sites(fablib):
    return [site for site in fablib.list_sites(output="list") if site.get("state") == "Active"]


def create_shared_nic_slice(site):
    with fim_lock:
        fablib = FablibManager(fabric_rc=fabric_rc)
        site_name = site["name"]
        slice_name = f"test-312-sharednic-{site_name.lower()}-{int(time.time())}"
        print(f"[{site_name}] Creating Shared NIC slice: {slice_name}")

        slice_obj = fablib.new_slice(name=slice_name)
        node = slice_obj.add_node(name="sharednic-node", site=site_name,
                                  cores=VM_CONFIG["cores"],
                                  ram=VM_CONFIG["ram"], disk=VM_CONFIG["disk"])
        # Attach a shared NIC
        node.add_component(model=NIC_MODEL, name="sharednic1")
        slice_obj.submit(wait=False)
        return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"[{slice_obj.get_name()}] Slice deletion error: {e}")


def test_create_shared_nic_vms_per_site(fablib):
    sites = get_active_sites(fablib)
    results = {}

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SITES) as executor:
        future_to_site = {}
        for site in sites:
            # Check if shared NICs are available (assume capacity key is known)
            if site.get("nic_basic_capacity", 0) == 0:
                continue
            future = executor.submit(create_shared_nic_slice, site)
            future_to_site[future] = site["name"]

        slice_objects = {}
        for future in as_completed(future_to_site):
            site_name = future_to_site[future]
            try:
                slice_obj = future.result()
                slice_objects[site_name] = slice_obj
            except Exception as e:
                print(f"[{site_name}] Slice submission error: {e}")
                traceback.print_exc()
                results[site_name] = False

    for site_name, slice_obj in slice_objects.items():
        try:
            slice_obj.wait(progress=False)
            slice_obj.wait_ssh(progress=False)
            slice_obj.post_boot_config()

            node = slice_obj.get_node("sharednic-node")

            print(f"[{site_name}] Checking Shared NIC device via lspci...")
            cmd = "sudo dnf install -y -q pciutils && lspci | grep -i Virtual"
            stdout, stderr = node.execute(cmd)
            assert "Mellanox Technologies" in stdout and "Virtual Function" in stdout, \
                f"[{site_name}] Shared NIC not detected"

            results[site_name] = True
        except Exception as e:
            print(f"[{site_name}] Shared NIC validation error: {e}")
            traceback.print_exc()
            results[site_name] = False

    for slice_obj in slice_objects.values():
        delete_slice(slice_obj)

    failed = [site for site, success in results.items() if not success]
    assert not failed, f"Shared NIC attachment failed on: {', '.join(failed)}"
