import pytest
import traceback
import time
from fabrictestbed_extensions.fablib.fablib import FablibManager
from concurrent.futures import ThreadPoolExecutor, as_completed
import os

fabric_rc = None
#os.environ['FABRIC_AVOID'] = 'UKY'
#fabric_rc = '/Users/kthare10/work/fabric_config_dev/fabric_rc'


SMART_NIC_MODELS = {
    'NIC_ConnectX_5': 'nic_connectx_5_capacity',
    'NIC_ConnectX_6': 'nic_connectx_6_capacity'
}
VM_CONFIG = {"cores": 10, "ram": 20, "disk": 50}
MAX_PARALLEL_SITES = 5


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_active_sites(fablib):
    return [site for site in fablib.list_sites(output="list") if site.get("state") == "Active"]


def create_smartnic_slice(site, nic_model):
    fablib = FablibManager(fabric_rc=fabric_rc)

    site_name = site["name"]
    slice_name = f"test-312-smartnic-{site_name.lower()}-{nic_model.lower()}-{int(time.time())}"
    print(f"[{site_name}] Creating Smart NIC slice: {slice_name}")

    slice_obj = fablib.new_slice(name=slice_name)
    node = slice_obj.add_node(name="smartnic-node", site=site_name,
                              cores=VM_CONFIG["cores"], ram=VM_CONFIG["ram"], disk=VM_CONFIG["disk"])
    node.add_component(model=nic_model, name="smartnic1")
    slice_obj.submit(wait=False)
    return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"[{slice_obj.get_name()}] Slice deletion error: {e}")


def test_create_smartnic_vms_per_site(fablib):
    sites = get_active_sites(fablib)
    results = {}

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SITES) as executor:
        future_to_site_model = {}
        for site in sites:
            for nic_model, capacity_key in SMART_NIC_MODELS.items():
                if site.get(capacity_key, 0) < 2:
                    continue
                future = executor.submit(create_smartnic_slice, site, nic_model)
                future_to_site_model[future] = (site["name"], nic_model)

        slice_objects = {}
        for future in as_completed(future_to_site_model):
            site_name, nic_model = future_to_site_model[future]
            key = f"{site_name}_{nic_model}"
            try:
                slice_obj = future.result()
                slice_objects[key] = slice_obj
            except Exception as e:
                print(f"[{key}] Slice submission error: {e}")
                traceback.print_exc()
                results[key] = False

    for key, slice_obj in slice_objects.items():
        try:
            slice_obj.wait(progress=False)
            slice_obj.wait_ssh(progress=False)
            slice_obj.post_boot_config()

            node = slice_obj.get_node("smartnic-node")

            print(f"[{key}] Checking Smart NIC devices via lspci...")
            cmd = "sudo dnf install -y -q pciutils && lspci"
            stdout, stderr = node.execute(cmd)

            assert ("ConnectX-6" in stdout or "ConnectX-5" in stdout), \
                f"[{key}] Smart NIC not detected in lspci"

            # Should see 4 entries: 2 cards × 2 ports
            nic_count = stdout.count("Ethernet controller: Mellanox Technologies")
            assert nic_count >= 2, f"[{key}] Expected >=2 NIC entries, found {nic_count}"

            results[key] = True
        except Exception as e:
            print(f"[{key}] Smart NIC validation error: {e}")
            traceback.print_exc()
            results[key] = False

    for slice_obj in slice_objects.values():
        delete_slice(slice_obj)

    failed = [key for key, success in results.items() if not success]
    assert not failed, f"Smart NIC attachment failed on: {', '.join(failed)}"
