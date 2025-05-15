import pytest
import traceback
import time
from fabrictestbed_extensions.fablib.fablib import FablibManager
from concurrent.futures import ThreadPoolExecutor, as_completed
from ipaddress import IPv4Network
from tests.base_test import fabric_rc, fim_lock


NIC_MODEL = 'NIC_ConnectX_5'
NIC_CAPACITY_FIELD = 'nic_connectx_5_capacity'
NETWORK_NAME = 'l2-STS'
SUBNET = IPv4Network("192.168.1.0/24")
MAX_PARALLEL = 2


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_sites_with_smartnic_workers(fablib):
    """Return sites with >=2 workers and Smart NIC capacity."""
    result = []
    for site in fablib.list_sites(output="list"):
        if site.get("state") != "Active":
            continue
        if site.get(NIC_CAPACITY_FIELD, 0) < 1:
            continue
        workers = site.get("hosts", [])
        if len(workers) >= 2:
            result.append((site["name"], sorted(workers)))
    return result


def make_site_triplets(sites):
    """Return site1, site2, worker1, worker2, worker3 tuples."""
    triplets = []
    for i in range(len(sites) - 1):
        site1, workers1 = sites[i]
        site2, workers2 = sites[i + 1]
        if len(workers1) >= 1 and len(workers2) >= 2:
            triplets.append((site1, site2, workers1[0], workers2[0], workers2[1]))
    return triplets


def create_l2sts_smartnic_slice(site1, site2, w1, w2, w3):
    with fim_lock:

        fablib = FablibManager(fabric_rc=fabric_rc)

        slice_name = f"test-323-l2sts-smartnic-{site1.lower()}-{site2.lower()}-{int(time.time())}"
        print(f"[{site1}/{site2}] Creating L2STS SmartNIC slice: {slice_name}")

        slice_obj = fablib.new_slice(name=slice_name)

        node1 = slice_obj.add_node(name="node1", site=site1, host=w1)
        iface1 = node1.add_component(model=NIC_MODEL, name="nic1").get_interfaces()[0]

        node2 = slice_obj.add_node(name="node2", site=site2, host=w2)
        iface2 = node2.add_component(model=NIC_MODEL, name="nic2").get_interfaces()[0]

        node3 = slice_obj.add_node(name="node3", site=site2, host=w3)
        iface3 = node3.add_component(model=NIC_MODEL, name="nic3").get_interfaces()[0]

        slice_obj.add_l2network(name=NETWORK_NAME, interfaces=[iface1, iface2, iface3], type='L2STS')
        slice_obj.submit(wait=False)
        return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"Deletion error: {e}")


def test_l2sts_smartnic_ping(fablib):
    results = {}
    slice_objects = {}
    available_ips = list(SUBNET)[1:]

    sites_with_workers = get_sites_with_smartnic_workers(fablib)
    triplets = make_site_triplets(sites_with_workers)

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as executor:
        future_to_triplet = {
            executor.submit(create_l2sts_smartnic_slice, site1, site2, w1, w2, w3): (site1, site2)
            for site1, site2, w1, w2, w3 in triplets
        }

        for future in as_completed(future_to_triplet):
            site1, site2 = future_to_triplet[future]
            key = f"{site1}-{site2}"
            try:
                slice_obj = future.result()
                slice_objects[key] = slice_obj
            except Exception as e:
                print(f"[{key}] Slice creation failed: {e}")
                traceback.print_exc()
                results[key] = False

    for key, slice_obj in slice_objects.items():
        try:
            slice_obj.wait(progress=False)
            slice_obj.wait_ssh(progress=False)
            slice_obj.post_boot_config()

            node1 = slice_obj.get_node("node1")
            node2 = slice_obj.get_node("node2")
            node3 = slice_obj.get_node("node3")

            iface1 = node1.get_interface(network_name=NETWORK_NAME)
            iface2 = node2.get_interface(network_name=NETWORK_NAME)
            iface3 = node3.get_interface(network_name=NETWORK_NAME)

            ip1 = str(available_ips.pop(0))
            ip2 = str(available_ips.pop(0))
            ip3 = str(available_ips.pop(0))

            iface1.ip_addr_add(addr=ip1, subnet=SUBNET)
            iface2.ip_addr_add(addr=ip2, subnet=SUBNET)
            iface3.ip_addr_add(addr=ip3, subnet=SUBNET)

            node1.execute(f"ip addr show {iface1.get_os_interface()}")
            node2.execute(f"ip addr show {iface2.get_os_interface()}")
            node3.execute(f"ip addr show {iface3.get_os_interface()}")

            node1.execute(f"ping -c 5 {ip2}")
            node1.execute(f"ping -c 5 {ip3}")
            node2.execute(f"ping -c 5 {ip3}")

            results[key] = True
        except Exception as e:
            print(f"[{key}] L2STS SmartNIC test failed: {e}")
            traceback.print_exc()
            results[key] = False

    for slice_obj in slice_objects.values():
        delete_slice(slice_obj)

    failed = [k for k, passed in results.items() if not passed]
    assert not failed, f"L2STS SmartNIC test failed on: {', '.join(failed)}"
