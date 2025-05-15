import pytest
import traceback
import time
from fabrictestbed_extensions.fablib.fablib import FablibManager
from concurrent.futures import ThreadPoolExecutor, as_completed
from ipaddress import IPv4Network

fabric_rc = None
#os.environ['FABRIC_AVOID'] = 'UKY'
#fabric_rc = '/Users/kthare10/work/fabric_config_dev/fabric_rc'

SMART_NIC_MODELS = ['NIC_ConnectX_5', 'NIC_ConnectX_6']
VM_CONFIG = {"cores": 10, "ram": 20, "disk": 50}
MAX_PARALLEL_SITES = 5
NETWORK_NAME = "l2-bridge"
SUBNET = IPv4Network("192.168.1.0/24")


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_active_sites(fablib):
    return [site for site in fablib.list_sites(output="list") if site.get("state") == "Active"]


def create_smartnic_bridge_slice(site, nic_type1, nic_type2):
    fablib = FablibManager(fabric_rc=fabric_rc)

    site_name = site["name"]
    slice_name = f"test-321-smartnic-{nic_type1.lower()}-{nic_type2.lower()}-{site_name.lower()}-{int(time.time())}"
    print(f"[{site_name}] Creating slice: {slice_name}")

    slice_obj = fablib.new_slice(name=slice_name)

    node1 = slice_obj.add_node(name="node1", site=site_name,
                               cores=VM_CONFIG["cores"], ram=VM_CONFIG["ram"], disk=VM_CONFIG["disk"])
    iface1 = node1.add_component(model=nic_type1, name="smartnic1").get_interfaces()[0]

    node2 = slice_obj.add_node(name="node2", site=site_name,
                               cores=VM_CONFIG["cores"], ram=VM_CONFIG["ram"], disk=VM_CONFIG["disk"])
    iface2 = node2.add_component(model=nic_type2, name="smartnic2").get_interfaces()[0]

    slice_obj.add_l2network(name=NETWORK_NAME, interfaces=[iface1, iface2])
    slice_obj.submit(wait=False)
    return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"[{slice_obj.get_name()}] Slice deletion error: {e}")


def test_smartnic_local_bridge_reachability(fablib):
    sites = get_active_sites(fablib)
    results = {}
    slice_objects = {}
    available_ips = list(SUBNET)[1:]

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SITES) as executor:
        future_to_site = {}
        for site in sites:
            connectx5 = site.get("nic_connectx_5_capacity", 0)
            connectx6 = site.get("nic_connectx_6_capacity", 0)
            if connectx5 >= 1 and connectx6 >= 1:
                future = executor.submit(create_smartnic_bridge_slice, site, "NIC_ConnectX_5", "NIC_ConnectX_6")
                future_to_site[future] = site["name"]

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

            node1 = slice_obj.get_node("node1")
            node2 = slice_obj.get_node("node2")

            # Assign IPs
            iface1 = node1.get_interface(network_name=NETWORK_NAME)
            ip1 = str(available_ips.pop(0))
            iface1.ip_addr_add(addr=ip1, subnet=SUBNET)
            node1.execute(f"ip addr show {iface1.get_os_interface()}")

            iface2 = node2.get_interface(network_name=NETWORK_NAME)
            ip2 = str(available_ips.pop(0))
            iface2.ip_addr_add(addr=ip2, subnet=SUBNET)
            node2.execute(f"ip addr show {iface2.get_os_interface()}")

            # Test reachability
            stdout, stderr = node1.execute(f"ping -c 5 {ip2}")
            assert "0% packet loss" in stdout, f"[{site_name}] Ping failed"
            results[site_name] = True

        except Exception as e:
            print(f"[{site_name}] Smart NIC bridge test failed: {e}")
            traceback.print_exc()
            results[site_name] = False

    for slice_obj in slice_objects.values():
        delete_slice(slice_obj)

    failed = [site for site, ok in results.items() if not ok]
    assert not failed, f"Smart NIC bridge test failed on: {', '.join(failed)}"
