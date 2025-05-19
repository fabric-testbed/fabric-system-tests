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
import json
import os
import random
import time
import traceback
from itertools import product, combinations
from concurrent.futures import ThreadPoolExecutor, as_completed
from fabrictestbed_extensions.fablib.fablib import FablibManager
from fabrictestbed_extensions.fablib.slice import Slice

from tests.base_test import fabric_rc, fim_lock

SLICE_PREFIX = "iperf@"
DEFAULT_IMAGE = "default_ubuntu_22"
NIC_MODEL = "NIC_Basic"
MAX_PARALLEL = 4
avoid = os.getenv('FABRIC_AVOID')
if not avoid or len(avoid) == 0:
    avoid = ["EDUKY"]

def get_fablib(fabric_rc=fabric_rc):
    return FablibManager(fabric_rc=fabric_rc)


def delete_existing_slices(fablib):
    for slice_obj in fablib.get_slices():
        if slice_obj.get_name().startswith(SLICE_PREFIX):
            print(f"Deleting existing slice: {slice_obj.get_name()}")
            try:
                slice_obj.delete()
            except Exception as e:
                print(f"Error deleting slice: {e}")


def get_sites_with_workers(fablib):
    return [site for site in fablib.list_sites(output="list") if site.get("state") == "Active"]


def create_slice(site, worker):
    site_name = site["name"]
    try:
        with fim_lock:
            fablib = get_fablib()

            slice_name = f"{SLICE_PREFIX}{site_name.lower()}-w{worker}-{int(time.time())}"
            slice_obj = fablib.new_slice(name=slice_name)
            node = slice_obj.add_node(name="node", site=site_name, cores=4, ram=16, disk=100,
                                      image="docker_rocky_8",
                                      host=f"{site_name.lower()}-w{worker}.fabric-testbed.net")
            node.add_fabnet(net_type="IPv4", nic_type='NIC_Basic')
            node.add_post_boot_upload_directory('../scripts/node_tools', '.')
            node.add_post_boot_execute('sudo node_tools/host_tune.sh')
            node.add_post_boot_execute('node_tools/enable_docker.sh {{ _self_.image }} ')

            try:
                slice_obj.validate()
            except Exception as e:
                print(f"Validation failed for {site_name}@{worker}: {e}")
                return f"{site_name}-{worker}", str(e)

            print(f"Submitting slice {slice_name}")
            slice_obj.submit(wait=False)
            return slice_name, slice_obj
    except Exception as e:
        print(f"Failed to create slice for {site_name}@{worker}: {e}")
        traceback.print_exc()
        return f"{site_name}-{worker}", str(e)


def create_site_worker_slices(fablib, sites):
    slices = {}
    failed_slices = {}

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        futures = {
            executor.submit(create_slice, site, worker): (site, worker)
            for site in sites
            if site["name"] not in avoid
            for worker in range(1, site["hosts"] + 1)
        }
        for future in as_completed(futures):
            site_worker = futures[future]
            try:
                slice_name, slice_obj_or_error = future.result()
                if isinstance(slice_obj_or_error, Slice):
                    slices[slice_name] = slice_obj_or_error
                else:
                    failed_slices[slice_name] = slice_obj_or_error
            except Exception as e:
                print(f"Exception for {site_worker}: {e}")
    return slices


def wait_and_configure_slices(slices):
    for name, slice_obj in slices.items():
        print(f"Waiting on slice {name}")
        try:
            slice_obj.wait()
            slice_obj.wait_ssh()
            slice_obj.post_boot_config()
        except Exception as e:
            print(f"[{name}] Slice configuration error: {e}")
            traceback.print_exc()


def get_site_pairs(slices):
    all_pairs = list(combinations(slices.keys(), 2))
    count = len(slices) // 2  # Automatically use half the number of slices
    if count > len(all_pairs):
        raise ValueError(f"Cannot select {count} unique pairs from only {len(all_pairs)} possible combinations.")
    return random.sample(all_pairs, count)


def collect_node_ips(slices):
    addrs = {}
    for name, slice_obj in slices.items():
        for node in slice_obj.get_nodes():
            ip = node.get_interface(network_name=f'FABNET_IPv4_{node.get_site()}').get_ip_addr()
            addrs[name] = str(ip)
        #ip = slice_obj.get_l3network("net").get_available_ips()[0]
        #addrs[name] = str(ip)
    return addrs


def run_remote_command(node, cmd):
    try:
        stdout, stderr = node.execute(cmd)
        return stdout.strip(), stderr.strip()
    except Exception as e:
        return "", str(e)


def cleanup_slices(slices):
    for name, slice_obj in slices.items():
        try:
            print(f"Deleting slice {name}")
            slice_obj.delete()
        except Exception as e:
            print(f"Error deleting slice {name}: {e}")


def save_results_json(results, filename="iperf_test_results.json"):
    with open(filename, "w") as f:
        json.dump(results, f, indent=2)
