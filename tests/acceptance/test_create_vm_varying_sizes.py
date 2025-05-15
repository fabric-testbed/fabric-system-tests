import traceback

import pytest
from fabrictestbed_extensions.fablib.fablib import FablibManager
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import os

VM_CONFIG = {
    "cores": 4,
    "ram": 8,    # GB
    "disk": 50,  # GB
}

MAX_WORKERS_PER_SITE = 1  # Limit to 1 VM per site for lightweight testing
MAX_PARALLEL_SITES = 5    # Max number of concurrent slice creations

fabric_rc = None
#os.environ['FABRIC_AVOID'] = 'UKY'
#fabric_rc = '/Users/kthare10/work/fabric_config_dev/fabric_rc'



@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_active_sites(fablib):
    return [site for site in fablib.list_sites(output="list") if site.get("state") == "Active"]


def create_and_submit_slice(fablib, site):
    """
    Create and submit a slice at the given site using non-blocking submit.
    Returns the slice object.
    """
    site_name = site["name"]
    worker_count = site["hosts"]
    slice_name = f"test311-{site_name.lower()}-{int(time.time())}"

    print(f"[{site_name}] Creating slice: {slice_name}")
    slice_obj = fablib.new_slice(name=slice_name)
    for w in range(1, worker_count+1):
        slice_obj.add_node(
            name=f"site_name.lower()-w{w}",
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
            executor.submit(create_and_submit_slice, fablib, site): site["name"]
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
