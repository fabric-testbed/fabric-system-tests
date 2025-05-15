import pytest
import re
import time
import shlex
from fabrictestbed_extensions.fablib.fablib import FablibManager
from tests.base_test import fabric_rc, fim_lock


SLICE_PREFIX = 'mtu@'
SITES_ONLY = ['GATECH', 'CLEM', 'GPN']  # modify if needed
NIC_MODEL = 'NIC_Basic'
PROBE_MTUS = [8900, 8948, 9000]

RE_LOSS = re.compile(r'(\d+)% packet loss')
RE_RTT = re.compile(r'rtt.*?=\s*[\d.]+/([\d.]+)/[\d.]+/[\d.]+ ms')

WIDTH_MTU = 4
WIDTH_RTT = 4
WIDTH_TD = WIDTH_MTU + WIDTH_RTT


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def list_mtu_slices(fablib):
    return {s.get_name()[len(SLICE_PREFIX):]: s for s in fablib.get_slices() if s.get_name().startswith(SLICE_PREFIX)}


def parse_ping_results(stdout, mtu_list):
    matches = list(RE_LOSS.finditer(stdout))
    if len(matches) != len(mtu_list):
        return 'ERR-RE'.ljust(WIDTH_TD)
    pass_mtu = 0
    for mtu, m in zip(mtu_list, matches):
        if m and m[1] == '0':
            pass_mtu = mtu
    rtt_match = RE_RTT.search(stdout)
    max_avg_rtt = int(float(rtt_match[1])) if rtt_match else -1
    return str(pass_mtu).ljust(WIDTH_MTU) + str(max_avg_rtt).rjust(WIDTH_RTT)


def test_mtu_probe(fablib):
    with fim_lock:
        existing_slices = list_mtu_slices(fablib)
        for site, slice_obj in existing_slices.items():
            print(f"[{site}] Deleting existing MTU slice")
            slice_obj.delete()

        slices = {}
        addrs = {}

        for site in SITES_ONLY:
            slice_obj = fablib.new_slice(name=SLICE_PREFIX + site)
            node = slice_obj.add_node(name='node', site=site, cores=1, ram=2, disk=10, image='default_ubuntu_22')

            intfs = node.add_component(model=NIC_MODEL, name='nic0').get_interfaces()
            if len(intfs) < 2:
                intfs += node.add_component(model=NIC_MODEL, name='nic1').get_interfaces()

            intf4, intf6 = intfs[:2]
            slice_obj.add_l3network(name='net4', interfaces=[intf4], type='IPv4')
            slice_obj.add_l3network(name='net6', interfaces=[intf6], type='IPv6')

            print(f"[{site}] Submitting slice")
            slice_obj.submit(wait=True)
            slice_obj.wait_ssh(progress=False)
            slice_obj.post_boot_config()
            slices[site] = slice_obj

        for site, slice_obj in slices.items():
            node = slice_obj.get_node('node')
            ipv4 = str(slice_obj.get_l3network('net4').get_available_ips()[0])
            ipv6 = str(slice_obj.get_l3network('net6').get_available_ips()[0])
            addrs[site] = {4: ipv4, 6: ipv6}
            print(f"[{site}] IPv4: {ipv4} | IPv6: {ipv6}")

        # Configure interfaces
        print("\nApplying interface configs...")
        for site, slice_obj in slices.items():
            node = slice_obj.get_node('node')
            cmds = []
            for af in [4, 6]:
                intf = node.get_interface(network_name=f'net{af}')
                devname = intf.get_os_interface()
                addr = addrs[site][af]
                net = intf.get_network()
                cmds += [
                    f"sudo ip link set {shlex.quote(devname)} up",
                    f"sudo ip link set {shlex.quote(devname)} mtu 9000",
                    f"sudo ip -{af} addr flush dev {shlex.quote(devname)}",
                    f"sudo ip -{af} addr add {shlex.quote(addr)}/{net.get_subnet().prefixlen} dev {shlex.quote(devname)}"
                ]
                for dst_site in slices:
                    if dst_site != site:
                        cmds.append(f"sudo ip -{af} route replace {addrs[dst_site][af]} via {net.get_gateway()}")
            stdout, stderr = node.execute('\n'.join(cmds))
            if stderr:
                print(f"[{site}] Interface config errors:\n{stderr}")

        # MTU probing
        results = {}
        for af, overhead in {4: 28, 6: 48}.items():
            print(f"\nIPv{af} ping MTU test results:")
            print("src\\dst".ljust(WIDTH_TD), end='')
            for dst in slices:
                print(f" | {dst.center(WIDTH_TD)}", end='')
            print()
            print('-' * (WIDTH_TD + 1) + ('|' + '-' * (WIDTH_TD + 2)) * len(slices))
            for src in slices:
                node = slices[src].get_node('node')
                row = src.ljust(WIDTH_TD)
                for dst in slices:
                    cmds = [
                        f"ping -I {addrs[src][af]} -c 4 -i 0.2 -W 0.8 -M do -s {mtu - overhead} {addrs[dst][af]}"
                        for mtu in PROBE_MTUS
                    ]
                    stdout, stderr = node.execute("\n".join(cmds))
                    row += " | " + parse_ping_results(stdout, PROBE_MTUS)
                print(row)

        # Cleanup
        print("\nDeleting all slices...")
        for site, slice_obj in slices.items():
            print(f"[{site}] Deleting slice")
            slice_obj.delete()
