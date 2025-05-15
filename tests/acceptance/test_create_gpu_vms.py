import traceback
import os
import pytest
import time
from fabrictestbed_extensions.fablib.fablib import FablibManager
from concurrent.futures import ThreadPoolExecutor, as_completed

fabric_rc = None
fabric_rc = '/Users/kthare10/work/fabric_config_dev/fabric_rc'
os.environ['FABRIC_AVOID'] = 'UKY'

GPU_MODELS = {
    'GPU_TeslaT4': 'tesla_t4_capacity',
    'GPU_RTX6000': 'rtx6000_capacity',
    'GPU_A30': 'a30_capacity',
    'GPU_A40': 'a40_capacity'
}

VM_CONFIG = {
    "cores": 6,
    "ram": 16,   # GB
    "disk": 50,  # GB
}

MAX_PARALLEL_SITES = 5    # Max number of concurrent slice creations
CUDA_VERSION = '12.6'
DISTRO = 'ubuntu2204'
ARCH = 'x86_64'


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_active_sites(fablib):
    return [site for site in fablib.list_sites(output="list") if site.get("state") == "Active"]


def create_and_submit_slice(site, gpu_model):
    """
    Create and submit a slice at the given site using non-blocking submit.
    Returns the slice object.
    """
    fablib = FablibManager(fabric_rc=fabric_rc)
    site_name = site["name"]
    slice_name = f"test-312-{site_name.lower()}-{gpu_model.lower()}-{int(time.time())}"

    print(f"[{site_name}] Creating slice: {slice_name}")
    slice_obj = fablib.new_slice(name=slice_name)
    node = slice_obj.add_node(name="gpu-node", site=site_name,
                              cores=VM_CONFIG["cores"], ram=VM_CONFIG["ram"], disk=VM_CONFIG["disk"],
                              image='default_ubuntu_24')
    node.add_component(model=gpu_model, name=f"gpu1-{gpu_model}")
    slice_obj.submit(wait=False)
    return slice_obj


def delete_slice(slice_obj):
    try:
        print(f"[{slice_obj.get_name()}] Deleting slice...")
        slice_obj.delete()
    except Exception as e:
        print(f"[{slice_obj.get_name()}] Slice deletion error: {e}")


def test_create_gpu_vms_per_site(fablib):
    distro = 'ubuntu2204'
    version = '12.6'
    architecture = 'x86_64'

    sites = get_active_sites(fablib)
    results = {}

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_SITES) as executor:
        future_to_site = {}
        for site in sites:
            for gpu_model, model_key in GPU_MODELS.items():
                if site.get(model_key, 0) == 0:
                    continue
                future = executor.submit(create_and_submit_slice, site, gpu_model)
                site_name = site["name"]
                future_to_site[future] = f"{site_name}_{gpu_model}"

        slice_objects = {}
        for future in as_completed(future_to_site):
            site_name_gpu_model = future_to_site[future]
            try:
                slice_obj = future.result()
                slice_objects[site_name_gpu_model] = slice_obj
            except Exception as e:
                print(f"[{site_name}] Error submitting slice: {e}")
                traceback.print_exc()
                results[site_name_gpu_model] = False

    # Wait for all slices to complete provisioning
    for site_name_gpu_model, slice_obj in slice_objects.items():
        slice_obj.wait(progress=False)
        slice_obj.wait_ssh(progress=False)
        slice_obj.post_boot_config()
        success = slice_obj.get_state() in ["StableOK", "StableError"]
        results[site_name_gpu_model] = success

        if success:
            try:
                node = slice_obj.get_node("gpu-node")
                slice_name = slice_obj.get_name()
                print(f"[{slice_name}] Installing CUDA and checking GPU...")

                setup_cmds = [
                    "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y pciutils && lspci | grep 'NVIDIA|3D controller'",
                    "sudo DEBIAN_FRONTEND=noninteractive apt-get -q update",
                    "sudo DEBIAN_FRONTEND=noninteractive apt-get -q install -y linux-headers-$(uname -r) gcc"
                    'sudo apt-get update -q',
                    'sudo apt-get install -y linux-headers-$(uname -r) gcc',
                    f'wget https://developer.download.nvidia.com/compute/cuda/repos/{distro}/{architecture}/cuda-keyring_1.1-1_all.deb',
                    f'sudo DEBIAN_FRONTEND=noninteractive dpkg -i cuda-keyring_1.1-1_all.deb',
                    f'sudo DEBIAN_FRONTEND=noninteractive apt-get -q update',
                    f'sudo apt-get -q install -y cuda-{version.replace(".", "-")}'
                ]

                for cmd in setup_cmds:
                    stdout, stderr = node.execute(cmd)

                reboot_cmd = "sudo reboot"
                print(f"[{slice_name}] Rebooting VM to finalize GPU setup...")
                node.execute(reboot_cmd)
                slice_obj.wait_ssh()
                slice_obj.update()
                slice_obj.test_ssh()

                print(f"[{slice_name}] Running nvidia-smi...")
                stdout, stderr = node.execute("nvidia-smi")
                assert "NVIDIA" in stdout, f"{slice_name} - GPU not detected by nvidia-smi"
            except Exception as e:
                print(f"[{site_name_gpu_model}] Validation error: {e}")
                results[site_name_gpu_model] = False

    # Cleanup
    for slice_obj in slice_objects.values():
        delete_slice(slice_obj)

    failed = [site for site, passed in results.items() if not passed]
    assert not failed, f"Slice with GPUs failed on: {', '.join(failed)}"
