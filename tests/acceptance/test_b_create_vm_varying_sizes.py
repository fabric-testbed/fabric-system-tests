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
import traceback

import pytest
from fabrictestbed_extensions.fablib.fablib import FablibManager
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
from tests.base_test import fabric_rc, fim_lock

VM_CONFIG = {
    "cores": 4,
    "ram": 8,    # GB
    "disk": 50,  # GB
}

MAX_WORKERS_PER_SITE = 1  # Limit to 1 VM per site for lightweight testing
MAX_PARALLEL_SITES = 5    # Max number of concurrent slice creations



@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_active_sites(fablib):
    return [site for site in fablib.list_sites(output="list") if site.get("state") == "Active"]


def create_and_submit_slice(site):
    """
    Create and submit a slice at the given site using non-blocking submit.
    Returns the slice object.
    """
    with fim_lock:

        fablib = FablibManager(fabric_rc=fabric_rc)
        site_name = site["name"]
        worker_count = site["hosts"]
        slice_name = f"test311-{site_name.lower()}-{int(time.time())}"

        print(f"[{site_name}] Creating slice: {slice_name}")
        slice_obj = fablib.new_slice(name=slice_name)
        for w in range(1, worker_count+1):
            slice_obj.add_node(
                name=f"{site_name.lower()}-w{w}",
                site=site_name,
                host=f"{site_name.lower()}-w{w}.fabric-testbed.net",
                cores=VM_CONFIG["cores"],
                ram=VM_CONFIG["ram"],
                disk=VM_CONFIG["disk"]
            )
        slice_obj.submit(wait=False)
        return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"[{slice_obj.get_name()}] Slice deletion error: {e}")


def test_non_blocking_vm_creation(fablib):
    sites = get_active_sites(fablib)
    results = {}

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SITES) as executor:
        future_to_site = {
            executor.submit(create_and_submit_slice, site): site["name"]
            for site in sites
        }

        slice_objects = {}
        for future in as_completed(future_to_site):
            site_name = future_to_site[future]
            try:
                slice_obj = future.result()
                slice_objects[site_name] = slice_obj
            except Exception as e:
                print(f"[{site_name}] Error submitting slice: {e}")
                traceback.print_exc()
                results[site_name] = False

    # Wait for all slices to complete provisioning
    for site_name, slice_obj in slice_objects.items():
        slice_obj.wait(progress=False)
        slice_obj.wait_ssh(progress=False)
        slice_obj.post_boot_config()
        success = slice_obj.get_state() in ["StableOK", "StableError"]
        results[site_name] = success

        if success:
            try:
                for node in slice_obj.get_nodes():
                    assert node.get_cores() >= VM_CONFIG["cores"]
                    assert node.get_ram() >= VM_CONFIG["ram"]
                    assert node.get_disk() >= VM_CONFIG["disk"]
            except Exception as e:
                print(f"[{site_name}] Validation error: {e}")
                results[site_name] = False

    # Cleanup
    for slice_obj in slice_objects.values():
        delete_slice(slice_obj)

    failed = [site for site, passed in results.items() if not passed]
    assert not failed, f"Slice creation failed on: {', '.join(failed)}"
