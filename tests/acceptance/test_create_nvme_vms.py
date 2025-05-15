import pytest
import traceback
import time
from fabrictestbed_extensions.fablib.fablib import FablibManager
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

fabric_rc = None
#os.environ['FABRIC_AVOID'] = 'UKY'
#fabric_rc = '/Users/kthare10/work/fabric_config_dev/fabric_rc'

NVME_MODEL = 'NVME_P4510'
VM_CONFIG = {"cores": 10, "ram": 20, "disk": 50}
MAX_PARALLEL_SITES = 5


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_active_sites(fablib):
    return [site for site in fablib.list_sites(output="list") if site.get("state") == "Active"]


def create_nvme_slice(fablib, site):
    site_name = site["name"]
    slice_name = f"test-312-nvme-{site_name.lower()}-{int(time.time())}"
    print(f"[{site_name}] Creating NVMe slice: {slice_name}")

    slice_obj = fablib.new_slice(name=slice_name)
    node = slice_obj.add_node(name="nvme-node", site=site_name,
                              cores=VM_CONFIG["cores"],
                              ram=VM_CONFIG["ram"], disk=VM_CONFIG["disk"])
    node.add_component(model=NVME_MODEL, name="nvme1")
    slice_obj.submit(wait=False)
    return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"[{slice_obj.get_name()}] Slice deletion error: {e}")


def test_create_nvme_vms_per_site(fablib):
    sites = get_active_sites(fablib)
    results = {}

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SITES) as executor:
        future_to_site = {}
        for site in sites:
            # Check NVME_P4510 availability before submitting
            if site.get('nvme_capacity', 0) < 2:
                continue
            future = executor.submit(create_nvme_slice, fablib, site)
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
            node = slice_obj.get_node("nvme-node")

            # Confirm NVMe devices are visible
            print(f"[{site_name}] Checking NVMe devices via lspci...")
            cmd = "sudo dnf install -y -q pciutils && lspci | grep -i nvme"
            stdout, stderr = node.execute(cmd)
            assert 'Non-Volatile memory controller' in stdout, f"[{site_name}] NVMe not detected"

            # Configure NVMe drives
            nvme1 = node.get_component("nvme1")
            nvme2 = node.get_component("nvme2")
            nvme1.configure_nvme()
            nvme2.configure_nvme()

            # Confirm partitions
            stdout, stderr = node.execute("sudo fdisk -l")
            assert "Disk /dev" in stdout, f"[{site_name}] No disk partitions found after configuration"

            results[site_name] = True
        except Exception as e:
            print(f"[{site_name}] NVMe validation error: {e}")
            traceback.print_exc()
            results[site_name] = False

    for slice_obj in slice_objects.values():
        delete_slice(slice_obj)

    failed = [site for site, success in results.items() if not success]
    assert not failed, f"NVMe attachment failed on: {', '.join(failed)}"
