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
from tests.daily.slice_helper import (
    get_fablib,
    delete_existing_slices,
    get_sites_with_workers,
    create_site_worker_slices,
    wait_and_configure_slices,
    get_site_pairs,
    collect_node_ips,
    run_remote_command,
    cleanup_slices,
    save_results_json
)

DOCKER_IMAGE = 'pruth/fabric-multitool-rockylinux9:latest'
RUN_TIME = 30

@pytest.fixture(scope="module")
def fablib():
    return get_fablib()


def test_site_worker_pair_ping_iperf(fablib):
    results = {}

    # Step 1: Cleanup any old slices
    delete_existing_slices(fablib)

    # Step 2: Discover all active sites and workers
    sites = get_sites_with_workers(fablib)

    # Step 3: Create slices for each (site, worker) pair
    slices = create_site_worker_slices(fablib, sites)

    # Step 4: Wait for all slices and configure them
    wait_and_configure_slices(slices)

    # Step 5: Collect IPs and define test pairs
    ip_map = collect_node_ips(slices)
    pairs = get_site_pairs(slices)

    print("\nRunning ping and iperf3 tests across all slice pairs...")

    for src, dst in pairs:
        if src == dst:
            continue  # Skip same-slice tests

        src_node = slices[src].get_node("node")
        dst_node = slices[dst].get_node("node")
        dst_ip = ip_map[dst]
        pair_key = f"{src}->{dst}"

        print(f"Testing {pair_key}...")

        pair_result = {"ping": None, "iperf3": None}

        # Ping test
        ping_cmd = f"ping -c 4 -W 1 {dst_ip}"
        ping_out, ping_err = run_remote_command(src_node, ping_cmd)
        if "0% packet loss" in ping_out:
            pair_result["ping"] = "PASS"
        else:
            pair_result["ping"] = f"FAIL: {ping_err or ping_out.strip().splitlines()[-1]}"

        # Start iperf3 server on destination
        iperf_cmd_server = f"docker run -d --rm --network host {DOCKER_IMAGE} iperf3 -s -1 > /dev/null 2>&1"
        run_remote_command(dst_node, iperf_cmd_server)

        # Run iperf3 client on source
        iperf_cmd_client = f"docker run --rm --network host {DOCKER_IMAGE} " \
                           f"iperf3 -c {dst_ip} -P 4 -t {RUN_TIME} -i 10 -O 10 -n 500M"
        iperf_out, iperf_err = run_remote_command(src_node, iperf_cmd_client)

        if "receiver" in iperf_out:
            pair_result["iperf3"] = "PASS"
        else:
            pair_result["iperf3"] = f"FAIL: {iperf_err or iperf_out.strip().splitlines()[-1]}"

        results[pair_key] = pair_result

    # Step 6: Save results
    save_results_json(results)

    # Step 7: Summary and cleanup
    failed = {pair: r for pair, r in results.items() if "FAIL" in r["ping"] or "FAIL" in r["iperf3"]}
    if failed:
        print("\nFailures:")
        for k, v in failed.items():
            print(f"{k}: {v}")
    else:
        print("\nAll site-worker pairs passed.")
        cleanup_slices(slices)

    assert not failed, f"Some slice pairs failed: {', '.join(failed.keys())}"
