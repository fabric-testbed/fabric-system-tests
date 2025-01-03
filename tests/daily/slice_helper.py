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
import ipaddress
import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


from fabrictestbed_extensions.fablib.fablib import FablibManager
from fabrictestbed_extensions.fablib.node import Node


class SliceHelper:
    """
    A helper class to manage and interact with slices in the FABRIC testbed.

    :param fablib_mgr: Manager for FABRIC slices and nodes.
    :type fablib_mgr: FablibManager
    :param slice_name_prefix: Prefix for slice names.
    :type slice_name_prefix: str
    :param sites: List of site names.
    :type sites: list
    :param skip_hosts: List of hosts to skip.
    :type skip_hosts: list
    :param docker_image: Docker image to use on nodes.
    :type docker_image: str
    :param wait: Whether to wait for slice actions to complete.
    :type wait: bool
    """
    def __init__(self, fablib_mgr: FablibManager, slice_name_prefix, sites, skip_hosts, docker_image, wait=True):
        self.go_time = False
        self.fablib_mgr = fablib_mgr
        self.slice_name_prefix = slice_name_prefix
        self.sites = sites
        self.skip_hosts = skip_hosts
        self.docker_image = docker_image
        self.wait = wait
        self.slice_ids = []
        self.future_tasks = {}
        self.all_slices = []
        self.all_nodes = []
        self.avoid_list = []
        self.details_of_failed_tests = []

    def configure_slice(self, slice_name=None, slice_id=None):
        """
        Configure an existing slice by its name or ID.

        :param slice_name: Name of the slice.
        :type slice_name: str, optional
        :param slice_id: ID of the slice.
        :type slice_id: str, optional
        :return: Configured slice object.
        :rtype: Slice
        """
        while not self.go_time:
            time.sleep(30)

        slice_object = None
        if slice_id or slice_name:
            slice_object = self.fablib_mgr.get_slice(slice_id=slice_id, name=slice_name)
            print(f" ({slice_object.get_name()})")

        if slice_object is None:
            print(f"slice_name or slice_id required!")
            return None

        slice_object.wait(progress=False)
        slice_object.wait_ssh(progress=False)
        slice_object.post_boot_config()
        return slice_object

    def create_and_submit_slices(self):
        """
        Create and submit slices based on the sites and hosts provided.
        Uses a ThreadPoolExecutor to handle multiple slices concurrently.
        """
        with ThreadPoolExecutor(max_workers=10) as executor:
            for index, site in enumerate(self.sites):
                host_count = self.fablib_mgr.get_resources().get_host_capacity(site)
                for host_num in range(host_count):
                    slice_name = f"{self.slice_name_prefix}_{index}_{site}_{host_num+1}"
                    slice_object = self.fablib_mgr.new_slice(name=slice_name)

                    host = f"{site.lower()}-w{host_num+1}.fabric-testbed.net"

                    if host in self.skip_hosts:
                        continue
                    print(f"Submitting {slice_name}: {host_count}")

                    for i in range(1):
                        node = slice_object.add_node(name=f"{site}-w{host_num+1}-{i+1}",
                                                     host=host,
                                                     site=site,
                                                     cores=4,
                                                     ram=16,
                                                     disk=100,
                                                     image="docker_rocky_8")

                        node.add_fabnet(net_type="IPv4", nic_type='NIC_Basic')
                        node.add_post_boot_upload_directory('../scripts/node_tools', '.')
                        node.add_post_boot_execute('sudo node_tools/host_tune.sh')    
                        node.add_post_boot_execute('node_tools/enable_docker.sh {{ _self_.image }} ')

                    try:
                        slice_object.validate()
                    except Exception as e:
                        print(e)
                        continue

                    slice_id = slice_object.submit(wait=self.wait)
                    self.slice_ids.append(slice_id)

                    try:
                        self.future_tasks[executor.submit(self.configure_slice, slice_id=slice_id)] = slice_object
                    except Exception as e:
                        print(f"{slice_name} not found")
                        print(e)
                        continue

            self.go_time = True
            for thread in as_completed(self.future_tasks.keys()):
                slice_object = self.future_tasks[thread]
                print(f"************ Configure {slice_object.get_name()}, done! **************** ")

    def process_slices(self):
        """
        Process all slices to ensure they are in a stable state.
        Lists nodes, networks, and interfaces for each slice.
        """
        print(f"slice count: {len(self.slice_ids)}")
        for slice_id in self.slice_ids:  
            try:
                print(f"slice: {slice_id}", end='')
                slice_object = self.fablib_mgr.get_slice(slice_id=slice_id)

                print(f" {slice_object.get_state()}")
                slice_object.list_nodes()

                if slice_object.get_state() not in ['StableOK']:
                    slice_object.show()
                    slice_object.list_nodes()
                    slice_object.list_networks()
                    slice_object.list_interfaces()

            except Exception as e:
                print(e)
                continue

        for index, site in enumerate(self.sites):
            host_count = self.fablib_mgr.get_resources().get_host_capacity(site)
            for host_num in range(host_count):
                slice_name = f"{self.slice_name_prefix}_{index}_{site}_{host_num+1}"
                host = f"{site.lower()}-w{host_num+1}.fabric-testbed.net"

                if host in self.skip_hosts:
                    continue

                print(slice_name)

                try: 
                    slice_object = self.fablib_mgr.get_slice(slice_name)
                except Exception as e:
                    print(e)
                    continue

                for node in slice_object.get_nodes():
                    try:
                        addr = node.get_interface(network_name=f'FABNET_IPv4_{node.get_site()}').get_ip_addr()
                        print(f"{node.get_name():<10} {str(node.get_management_ip()):<40}  {str(addr):<16}")
                        stdout, stderr = node.execute('echo Hello, FABRIC from node `hostname -s`', quiet=False)
                    except Exception as e:
                        print(e)
                        continue

        for slice_id in self.slice_ids:   
            try:
                print(f"slice: {slice_id}", end='')
                slice_object = self.fablib_mgr.get_slice(slice_id=slice_id)

                print(f" {slice_object.get_state()}")

                if slice_object.get_state() not in ['StableOK']:
                    print(f" ({slice_object.get_name()})")
                    print(f" ({slice_object.get_error_messages()})")
                    continue

            except Exception as e:
                print(e)
                continue 

            self.all_slices.append(slice_object)

            for node in slice_object.get_nodes():
                self.all_nodes.append(node)

    def capture_failure(self, source: Node, target: Node, source_addr: ipaddress, target_addr: ipaddress):
        """
        Capture details of a failed test.

        :param source: The source node.
        :type source: Node
        :param target: The target node.
        :type target: Node
        :param source_addr: The IP address of the source node.
        :type source_addr: str
        :param target_addr: The IP address of the target node.
        :type target_addr: str
        """
        failed_test_detail = {
            "slice": {
                "name": source.get_slice().get_name(),
                "id": source.get_slice().get_slice_id()
            },
            "source": {
                "name": source.get_name(),
                "address": str(source_addr),
                "ssh_command": source.get_ssh_command()
            },
            "target": {
                "name": target.get_name(),
                "address": str(target_addr),
                "ssh_command": target.get_ssh_command()
            }
        }

        # Append to the global list
        self.details_of_failed_tests.append(failed_test_detail)

    # After all tests, dump the captured details to a JSON file
    def dump_failed_tests_to_json(self, file_path="../results/failed_tests.json"):
        """
        Dump all captured failed test details to a JSON file.

        :param file_path: File path for the JSON output.
        :type file_path: str
        """
        with open(file_path, "w") as json_file:
            json.dump(self.details_of_failed_tests, json_file, indent=4)

    def run_tests(self, run_iperf: bool = False, run_time: int = 30):
        """
        Run tests between nodes in the slices.

        :param run_iperf: Whether to run iperf tests.
        :type run_iperf: bool
        :param run_time: Duration for iperf tests, in seconds.
        :type run_time: int
        :return: True if all tests pass, otherwise False.
        :rtype: bool
        """
        if len(self.all_nodes) == 0:
            return False
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_tasks = {}

            for i in range(min(len(self.all_nodes), 400)):
                try:
                    source = random.choice(self.all_nodes)
                    target = random.choice(self.all_nodes)

                    if source.get_site() in self.avoid_list or target.get_site() in self.avoid_list:
                        continue

                    run_name = f"run_{source.get_name()}_{target.get_name()}"
                    print(f"({i}) Running: {run_name} \t", end="")

                    if run_iperf and source != target:
                        stdout1, stderr1 = source.execute("docker run -d --rm "
                                                          "--network host "
                                                          f"{self.docker_image} "
                                                          "iperf3 -s -1", quiet=True)

                    target_addr = target.get_interface(network_name=f'FABNET_IPv4_{target.get_site()}').get_ip_addr()
                    source_addr = source.get_interface(network_name=f'FABNET_IPv4_{source.get_site()}').get_ip_addr()

                    stdout2a, stderr2a = target.execute(f"ping -c 3 {source_addr} > /dev/null ; ping -c 3 {source_addr} > /dev/null ; echo $?", quiet=True)
                    stdout2a = stdout2a.strip()

                    if stdout2a == '0':
                        print(f"Success!")
                    else:

                        slice_object = source.get_slice()
                        if source == target:
                            source.get_slice().post_boot_config()
                            stdout2a, stderr2a = target.execute(f"ping -c 10 {target_addr} > /dev/null ", quiet=False)
                            print(f"Skip!!, {source} == {target}")
                            continue
                        else:
                            try:
                                future_tasks[executor.submit(self.configure_slice, slice_id=source.get_slice().get_slice_id())] = slice_object
                            except Exception as e:
                                print(f"{slice_object.get_name()} not found")
                                print(e)

                        '''
                        slice_object = source.get_slice()
                        slice_object.show()
                        slice_object.list_nodes()
                        slice_object.list_networks()
                        slice_object.list_interfaces()
                        '''

                        print(f"Fail!!, Source slice: {source.get_slice().get_name()}/{source.get_slice().get_slice_id()} "
                              f"Target Slice: {target.get_slice().get_name()}/{target.get_slice().get_slice_id()}")
                        print(f"Source: {source.get_name()}: {source_addr}")
                        print(f"{source.get_ssh_command()}")
                        print(f"Target: {target.get_name()}: {target_addr}")
                        print(f"{target.get_ssh_command()}")

                        self.capture_failure(source=source, source_addr=source_addr, target=target,
                                             target_addr=target_addr)

                    if not run_iperf:
                        continue

                    stdout2, stderr2 = target.execute("docker run --rm "
                                                      "--network host "
                                                      f"{self.docker_image} "
                                                      f"iperf3 -c {source_addr} -P 4 -t {run_time} -i 10 -O 10", 
                                                      quiet=True, output_file=f"../results/{run_name}.log")

                    lines = stdout2.splitlines()

                    with open('../results/summary.txt', 'a') as file:
                        file.write(run_name + "\n")
                        file.write(str(stdout2a) + "\n")

                        if len(lines) >= 3:
                            last_line = lines[-3]
                            print(last_line)
                            file.write(last_line + "\n")
                        else:
                            print(stdout2)
                            file.write(str(stdout2) + "\n")

                except Exception as e:
                    print(e)
                    continue

        if len(self.details_of_failed_tests):
            self.dump_failed_tests_to_json()
            return False

        return True

    def run(self, run_iperf: bool = False):
        """
        Run the full workflow: create slices, process slices, and run tests.

        :param run_iperf: Whether to include iperf tests.
        :type run_iperf: bool
        :return: True if all steps succeed, otherwise False.
        :rtype: bool
        """
        self.create_and_submit_slices()
        self.process_slices()
        return self.run_tests(run_iperf=run_iperf)
