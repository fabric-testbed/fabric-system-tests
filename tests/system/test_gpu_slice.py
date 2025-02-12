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
from tests.base_test import BaseTest


class GpuSliceTest(BaseTest):
    def setUp(self):
        self.prefix = "Gpu"
        super(GpuSliceTest, self).setUp()

    def test_slice(self):
        GPU_CHOICE = 'GPU_RTX6000'

        # don't edit - convert from GPU type to a resource column name
        # to use in filter lambda function below
        choice_to_column = {
            "GPU_RTX6000": "rtx6000_available",
            "GPU_TeslaT4": "tesla_t4_available",
            "GPU_A30": "a30_available",
            "GPU_A40": "a40_available"
        }

        column_name = choice_to_column.get(GPU_CHOICE, "Unknown")
        print(f'{column_name=}')
        node_name = 'gpu-node'
        site = self._fablib.get_random_site(filter_function=lambda x: x[column_name] > 0)

        # Add node with a 100G drive and a couple of CPU cores (default)
        node = self._slice.add_node(name=node_name, site=site, disk=100, image='default_ubuntu_24')
        node.add_component(model=GPU_CHOICE, name='gpu1')

        # Submit Slice Request
        self._slice.submit()

        # VERIFICATION
        self._slice.update()
        self.check_slice(node_cnt=1, network_cnt=0)

        node = self._slice.get_node(node_name)

        gpu = node.get_component('gpu1')
        self.assertIsNotNone(gpu, "GPU not found")

        command = "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y pciutils && lspci | grep 'NVIDIA|3D controller'"
        stdout, stderr = node.execute(command)
        self.assertEqual("", stderr, "apt-get install failed")

        distro = 'ubuntu2204'
        version = '12.6'
        architecture = 'x86_64'

        # install prerequisites
        commands = [
            'sudo DEBIAN_FRONTEND=noninteractive apt-get -q update',
            'sudo DEBIAN_FRONTEND=noninteractive apt-get -q install -y linux-headers-$(uname -r) gcc',
        ]

        print("Installing Prerequisites...")
        for command in commands:
            print(f"++++ {command}")
            stdout, stderr = node.execute(command)

        print(f"Installing CUDA {version}")
        commands = [
            f'wget https://developer.download.nvidia.com/compute/cuda/repos/{distro}/{architecture}/cuda-keyring_1.1-1_all.deb',
            f'sudo DEBIAN_FRONTEND=noninteractive dpkg -i cuda-keyring_1.1-1_all.deb',
            f'sudo DEBIAN_FRONTEND=noninteractive apt-get -q update',
            f'sudo apt-get -q install -y cuda-{version.replace(".", "-")}'
        ]
        print("Installing CUDA...")
        for command in commands:
            print(f"++++ {command}")
            stdout, stderr = node.execute(command)

        print("Done installing CUDA")

        reboot = 'sudo reboot'

        print(reboot)
        node.execute(reboot)

        self._slice.wait_ssh(timeout=500, interval=10, progress=True)

        node = self._slice.get_node(node_name)
        print("Now testing SSH abilities to reconnect...", end="")
        self._slice.update()
        self._slice.test_ssh()
        print("Reconnected!")

        stdout, stderr = node.execute("nvidia-smi")
        self.assertEqual("", stderr, "nvidia-smi  failed")

        '''
        node.upload_file('../scripts/gpu_files/hello-world.cu', 'hello-world.cu')
        stdout, stderr = node.execute(f"/usr/local/cuda-{version}/bin/nvcc -o hello_world hello-world.cu")
        self.assertEqual("", stderr, "hello world build failed")

        stdout, stderr = node.execute("./hello_world")
        self.assertEqual("", stderr, "hello world cuda failed")
        '''

        # VERIFICATION
        self._slice.delete()
