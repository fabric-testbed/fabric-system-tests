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
from tests.base_test import fabric_rc


VM_CONFIG = {"cores": 10, "ram": 20, "disk": 50}
STORAGE_NAME = "acceptance-testing"
WORKER_SUFFIX = "w1.fabric-testbed.net"
MAX_PARALLEL_SITES = 5


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_active_sites(fablib):
    return [site for site in fablib.list_sites(output="list") if site.get("state") == "Active"]


def create_storage_slice(site):
    with fim_lock:

        fablib = FablibManager(fabric_rc=fabric_rc)
        site_name = site["name"]
        worker = f"{site_name.lower()}-{WORKER_SUFFIX}"
        slice_name = f"test-313-storage-{site_name.lower()}-{int(time.time())}"
        print(f"[{site_name}] Creating slice: {slice_name}")

        slice_obj = fablib.new_slice(name=slice_name)
        node = slice_obj.add_node(name="storage-node", site=site_name,
                                  host=worker, cores=VM_CONFIG["cores"],
                                  ram=VM_CONFIG["ram"], disk=VM_CONFIG["disk"])
        node.add_storage(name=STORAGE_NAME)
        slice_obj.submit(wait=False)
        return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"[{slice_obj.get_name()}] Slice deletion error: {e}")


def test_attached_storage_parallel(fablib):
    sites = get_active_sites(fablib)
    results = {}
    slice_objects = {}

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SITES) as executor:
        future_to_site = {
            executor.submit(create_storage_slice, site): site["name"]
            for site in sites
        }

        for future in as_completed(future_to_site):
            site_name = future_to_site[future]
            try:
                slice_obj = future.result()
                slice_objects[site_name] = slice_obj
            except Exception as e:
                print(f"[{site_name}] Slice submission failed: {e}")
                traceback.print_exc()
                results[site_name] = False

    for site_name, slice_obj in slice_objects.items():
        try:
            slice_obj.wait(progress=False)
            slice_obj.wait_ssh(progress=False)
            slice_obj.post_boot_config()

            node = slice_obj.get_node("storage-node")
            storage = node.get_storage(STORAGE_NAME)
            device = storage.get_device_name()
            print(f"[{site_name}] Storage device: {device}")

            # Format volume
            node.execute(f"sudo mkfs.ext4 {device}")

            # Mount volume
            node.execute(
                f"sudo mkdir -p /mnt/fabric_storage && "
                f"sudo mount {device} /mnt/fabric_storage && "
                f"df -h"
            )

            # Verify write
            node.execute("sudo dd if=/dev/zero of=/mnt/fabric_storage/zero-file bs=1024 count=1024")
            stdout, _ = node.execute("ls -lh /mnt/fabric_storage")
            assert "zero-file" in stdout, f"[{site_name}] Write verification failed"

            results[site_name] = True
        except Exception as e:
            print(f"[{site_name}] Storage test failed: {e}")
            traceback.print_exc()
            results[site_name] = False

    for slice_obj in slice_objects.values():
        delete_slice(slice_obj)

    failed = [site for site, ok in results.items() if not ok]
    assert not failed, f"Attached storage test failed on: {', '.join(failed)}"
