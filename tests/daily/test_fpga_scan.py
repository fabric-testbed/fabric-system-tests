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
# Author: sankarang@renci.org
"""Daily FPGA discovery scan.

Answers three questions the site-level resource tables cannot:

  * which specific worker holds an FPGA, and of which model;
  * is that card free right now, or reserved by another slice;
  * can a user actually launch an FPGA VM on that worker.

The third question is the one that bites. A site can advertise hundreds of
free cores while the single worker carrying the card has none, and submit()
then fails late with "Insufficient resources : [core]". So every figure here
is per worker, never per site.

Models are discovered from the resource graph rather than listed in code, so
an FPGA type the testbed adds later is scanned without a change here. Nothing
is judged against a particular runtime: the scan reports what is present and
whether it can be obtained, not whether some vendor's toolchain would bind it.

Run it:

    pytest tests/daily/test_fpga_scan.py            # inventory only, no allocation
    python -m tests.daily.test_fpga_scan            # same, outside pytest

    FPGA_SCAN_LAUNCH=TRUE pytest tests/daily/test_fpga_scan.py   # also launch a VM

Both forms run from the repo root. Environment:

    FPGA_SCAN_SITES            space/comma separated sites, default all
    FPGA_SCAN_LAUNCH           TRUE to provision a probe VM per host, default FALSE
    FPGA_SCAN_LAUNCH_MAX_HOSTS upper bound on probe VMs, default 1
    FPGA_SCAN_KEEP_FAILED      TRUE to keep a failed probe slice for inspection
"""

import os
import time
import traceback

import pytest

from fabrictestbed_extensions.fablib.fablib import FablibManager

from tests.base_test import fabric_rc, fim_lock
from tests.utils import error_message, save_results_json

# Inventory keys use dashes (FPGA-Xilinx-U280); add_component() takes
# underscores (FPGA_Xilinx_U280). Both spellings appear below, deliberately.
FPGA_PREFIX = 'FPGA'
FPGA_COLUMN_PREFIX = 'fpga_'

# A probe VM is deliberately tiny. It only reads the card's state, and the
# worker holding an FPGA is routinely the fullest machine at its site.
PROBE_CORES = 2
PROBE_RAM = 8
PROBE_DISK = 50
PROBE_IMAGE = 'default_ubuntu_22'
PROBE_NODE = 'fpga-probe'

# Vendor ids used only to label lspci output, never to grade a card.
PCI_VENDORS = {'10ee': 'Xilinx/AMD', '1172': 'Altera/Intel'}

INVENTORY_JSON = 'fpga_scan.json'
LAUNCH_JSON = 'fpga_launch.json'

SCAN_SITES = [s for s in os.getenv('FPGA_SCAN_SITES', '').replace(',', ' ').split() if s]
LAUNCH_ENABLED = os.getenv('FPGA_SCAN_LAUNCH', 'FALSE').upper() == 'TRUE'
LAUNCH_MAX_HOSTS = int(os.getenv('FPGA_SCAN_LAUNCH_MAX_HOSTS', '1'))
KEEP_FAILED = os.getenv('FPGA_SCAN_KEEP_FAILED', 'FALSE').upper() == 'TRUE'

VERDICT_HELP = {
    'AVAILABLE': 'a card is free and the worker has room for an FPGA VM',
    'RESERVED': 'every card on this worker is held by another slice',
    'NO-ROOM': 'a card is free but the worker cannot fit even a minimal VM',
    'MAINTENANCE': 'worker is in maintenance; the card cannot be requested',
    'HOST-DOWN': 'worker is not in Active state',
}
VERDICT_ORDER = ['AVAILABLE', 'RESERVED', 'NO-ROOM', 'MAINTENANCE', 'HOST-DOWN']


def column_to_inventory_key():
    """Map flattened column stems (fpga_u280) back to inventory keys
    (FPGA-Xilinx-U280) using FABlib's own table, so no model is named here.
    """
    mapping = {}
    try:
        from fabrictestbed_extensions.fablib.constants import Constants
        from fabrictestbed_extensions.fablib.site import ResourceConstants
    except ImportError:
        return mapping
    for key, names in ResourceConstants.attribute_name_mappings.items():
        if str(key).upper().startswith(FPGA_PREFIX):
            mapping[names.get(Constants.NON_PRETTY_NAME)] = key
    return mapping


def host_free(host, stem):
    """cores/ram/disk free on one worker -- the numbers that decide whether a
    VM can actually land on the machine holding the card.
    """
    for key in (f'{stem}s_available', f'{stem}_available'):
        if key in host:
            try:
                return max(0, int(host.get(key) or 0))
            except (TypeError, ValueError):
                return 0
    capacity = host.get(f'{stem}s_capacity', host.get(f'{stem}_capacity')) or 0
    allocated = host.get(f'{stem}s_allocated', host.get(f'{stem}_allocated')) or 0
    try:
        return max(0, int(capacity) - int(allocated))
    except (TypeError, ValueError):
        return 0


def fpga_counts(host):
    """Return {inventory_key: (capacity, allocated, available)} for every FPGA
    on one worker, of any model.

    Two host-dict shapes are in the wild: a nested components dict keyed by the
    inventory name, and flattened <stem>_capacity columns. Reading only one of
    them is how a scan quietly reports zero FPGAs everywhere.
    """
    found = {}
    for key, entry in (host.get('components') or {}).items():
        if not str(key).upper().startswith(FPGA_PREFIX) or not isinstance(entry, dict):
            continue
        capacity = int(entry.get('capacity') or 0)
        allocated = int(entry.get('allocated') or 0)
        available = entry.get('available')
        available = capacity - allocated if available is None else int(available)
        found[key] = (capacity, allocated, max(0, available))
    if found:
        return found

    stems = column_to_inventory_key()
    for key in host:
        if not str(key).startswith(FPGA_COLUMN_PREFIX) or not str(key).endswith('_capacity'):
            continue
        stem = key[:-len('_capacity')]
        capacity = int(host.get(key) or 0)
        allocated = int(host.get(f'{stem}_allocated') or 0)
        available = host.get(f'{stem}_available')
        available = capacity - allocated if available is None else int(available)
        found[stems.get(stem, stem)] = (capacity, allocated, max(0, available))
    return found


def classify(host, counts, free):
    """Return (verdict, reason) for one card on one worker."""
    capacity, _allocated, available = counts
    state = host.get('state') or 'Unknown'
    if host.get('in_maintenance'):
        return 'MAINTENANCE', 'worker is in maintenance'
    if state not in ('Active', 'Unknown'):
        return 'HOST-DOWN', f'worker state is {state}'
    if available < 1:
        return 'RESERVED', f'all {capacity} card(s) held by another slice'
    short = []
    if free['cores'] < PROBE_CORES:
        short.append(f"{free['cores']} of {PROBE_CORES} cores")
    if free['ram'] < PROBE_RAM:
        short.append(f"{free['ram']} of {PROBE_RAM} GB ram")
    if free['disk'] < PROBE_DISK:
        short.append(f"{free['disk']} of {PROBE_DISK} GB disk")
    if short:
        return 'NO-ROOM', 'card free but worker has only ' + ', '.join(short)
    return 'AVAILABLE', f'{available} of {capacity} card(s) free'


def scan_fpga_inventory(fablib):
    """Walk every site's workers and return one record per (worker, model).

    Resource queries only: nothing is provisioned and nothing is billed.
    """
    print('Querying the FABRIC resource model (no slices involved)')
    resources = fablib.get_resources()
    site_names = sorted(resources.get_site_names() or [])

    if SCAN_SITES:
        wanted = {name.upper() for name in SCAN_SITES}
        missing = wanted - {name.upper() for name in site_names}
        for name in sorted(missing):
            print(f"[{name}] not advertised by the testbed, skipping")
        site_names = [name for name in site_names if name.upper() in wanted]

    records = []
    for site_name in site_names:
        site = resources.get_site(site_name) or {}
        try:
            hosts = resources.get_hosts_by_site(site_name) or {}
        except Exception as e:
            print(f"[{site_name}] could not list hosts: {e}")
            continue
        for host_name, host in sorted(hosts.items()):
            counts_by_model = fpga_counts(host)
            if not counts_by_model:
                continue
            free = {'cores': host_free(host, 'core'),
                    'ram': host_free(host, 'ram'),
                    'disk': host_free(host, 'disk')}
            for model, counts in sorted(counts_by_model.items()):
                capacity, allocated, available = counts
                if capacity == 0:
                    continue
                verdict, reason = classify(host, counts, free)
                records.append({
                    'site': site_name,
                    'site_state': site.get('state') or 'Unknown',
                    'host': host_name,
                    'host_state': host.get('state') or 'Unknown',
                    'in_maintenance': bool(host.get('in_maintenance')),
                    'model': model,
                    'fpga_capacity': capacity,
                    'fpga_allocated': allocated,
                    'fpga_available': available,
                    'cores_available': free['cores'],
                    'ram_available': free['ram'],
                    'disk_available': free['disk'],
                    'verdict': verdict,
                    'reason': reason,
                })
    return records


def print_inventory_summary(records):
    print('TEST SUMMARY==========================================================================================')
    if not records:
        print('No worker at any scanned site advertises an FPGA of any model.')
        return
    for site_name in sorted({r['site'] for r in records}):
        rows = sorted((r for r in records if r['site'] == site_name), key=lambda r: r['host'])
        free = sum(r['fpga_available'] for r in rows)
        capacity = sum(r['fpga_capacity'] for r in rows)
        # Count distinct workers, not records: one worker can carry two models.
        workers = len({r['host'] for r in rows})
        print(f"\n  {site_name}  {free}/{capacity} card(s) free across {workers} worker(s)")
        for r in rows:
            flag = '!' if r['in_maintenance'] else ' '
            print(f"  {flag} {r['host'].split('.')[0]:<16} {r['model']:<20} "
                  f"{r['fpga_available']:>2}/{r['fpga_capacity']:<2} "
                  f"cores={r['cores_available']:<4} ram={r['ram_available']:<4} "
                  f"disk={r['disk_available']:<4} {r['verdict']} - {r['reason']}")
    verdicts = {}
    for r in records:
        verdicts[r['verdict']] = verdicts.get(r['verdict'], 0) + 1
    total_free = sum(r['fpga_available'] for r in records)
    total_capacity = sum(r['fpga_capacity'] for r in records)
    print(f"\n  TOTAL: {total_free}/{total_capacity} card(s) free on "
          f"{len({r['host'] for r in records})} worker(s) "
          f"across {len({r['site'] for r in records})} site(s)")
    counted = [(v, verdicts[v]) for v in VERDICT_ORDER if v in verdicts]
    print('  BY STATE: ' + ',  '.join(f'{v}={n}' for v, n in counted))
    for verdict, _ in counted:
        print(f"    {verdict:<14} {VERDICT_HELP[verdict]}")
    models = sorted({r['model'] for r in records})
    print(f"  MODELS DISCOVERED: {', '.join(models)}")


def read_card_state(node):
    """Collect what the VM can see about its FPGA, without judging it.

    Descriptive on purpose: device ids, classes and bound drivers are reported
    verbatim rather than graded, because whether a card is 'usable' depends on
    the runtime a given experiment brings with it.
    """
    facts = {}
    node.execute('sudo apt-get install -y -qq pciutils || sudo dnf install -q -y pciutils',
                 quiet=True)
    stdout, _stderr = node.execute('lspci -nn', quiet=True)
    facts['accelerators'] = [
        line.strip() for line in (stdout or '').splitlines()
        if any(f'[{vendor}:' in line.lower() for vendor in PCI_VENDORS)
        or 'processing accelerator' in line.lower()
    ]
    stdout, _stderr = node.execute(
        'lspci -nnk | grep -A3 -i -E "processing accelerator|xilinx|altera" || true', quiet=True)
    facts['drivers'] = (stdout or '').strip()
    stdout, _stderr = node.execute(
        'ls -1 /dev/xdma* /dev/fpga* /dev/dri/renderD* 2>/dev/null || true', quiet=True)
    facts['device_nodes'] = (stdout or '').split()
    # Vendor tooling is captured if present and never parsed: the same query
    # prints 'Device(s) Present' on XRT 2.19 and 'Devices present' on 2.16, so
    # grepping for either string under-reports on the other version.
    stdout, _stderr = node.execute(
        'command -v xbutil >/dev/null && xbutil examine 2>&1 || true', quiet=True)
    facts['vendor_tool'] = (stdout or '').strip()[:4000]
    return facts


def slice_id(slice_obj, slice_name):
    try:
        return f"{slice_name}/{slice_obj.get_slice_id()}"
    except Exception:
        return slice_name


def delete_probe_slice(slice_obj, slice_name, passed):
    """Release the card.

    Unlike the GPU and NVMe tests, a failed FPGA probe slice is deleted rather
    than kept for inspection: a worker carries one or two cards for the whole
    testbed, so a retained slice blocks every other user. Override with
    FPGA_SCAN_KEEP_FAILED=TRUE.
    """
    if slice_obj is None:
        return
    if not passed and KEEP_FAILED:
        print(f"[{slice_name}] keeping failed slice for inspection")
        return
    try:
        print(f"[{slice_name}] deleting probe slice and releasing the card")
        slice_obj.delete()
    except Exception as e:
        print(f"[{slice_name}] delete failed: {e}")


def launch_probe(fablib, record):
    """Submit one minimal VM pinned to the worker holding the card.

    This is the only honest answer to "can a user get an FPGA VM here". The
    inventory pass can say a VM should fit; placement, image priming and PCI
    passthrough all fail after submit() if they fail at all.
    """
    host = record['host']
    short_host = host.split('.')[0]
    model = record['model'].replace('-', '_')
    slice_name = f"ST-Slice-FpgaScan-{short_host}-{int(time.time())}"
    slice_obj = None
    placed = False
    try:
        with fim_lock:
            slice_obj = fablib.new_slice(name=slice_name)
        # host= is the load-bearing argument. Without it the testbed may place
        # the VM on any worker at the site, and only one of them has the card.
        node = slice_obj.add_node(name=PROBE_NODE, site=record['site'], host=host,
                                  cores=PROBE_CORES, ram=PROBE_RAM, disk=PROBE_DISK,
                                  image=PROBE_IMAGE)
        node.add_component(model=model, name='fpga1')
        print(f"[{short_host}] submitting {slice_name} with {model}")
        slice_obj.submit()
        slice_obj.update()
        state = str(slice_obj.get_state())
        if state != 'StableOK':
            return {'state': False, 'launched': False,
                    'error': f"slice state {state}: {error_message(slice_obj=slice_obj)}",
                    'slice_id': slice_id(slice_obj, slice_name), 'card': {}}
        placed = True
        slice_obj.wait_ssh(progress=False)
        # Handles built before submit() are stale descriptors; the live ones
        # only exist after re-fetching the slice.
        slice_obj = fablib.get_slice(name=slice_name)
        node = slice_obj.get_node(name=PROBE_NODE)
        card = read_card_state(node)
        print(f"[{short_host}] VM launched; {len(card['accelerators'])} accelerator "
              f"function(s) visible in the VM")
        return {'state': True, 'launched': True, 'error': '',
                'slice_id': slice_id(slice_obj, slice_name), 'card': card}
    except Exception as e:
        print(f"[{short_host}] {'probe' if placed else 'launch'} failed: {e}")
        traceback.print_exc()
        message = error_message(slice_obj=slice_obj, exception=e) if slice_obj else str(e)
        return {'state': False, 'launched': placed, 'error': message,
                'slice_id': slice_id(slice_obj, slice_name) if slice_obj else slice_name,
                'card': {}}
    finally:
        delete_probe_slice(slice_obj, slice_name, placed)


@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def test_fpga_inventory(fablib):
    records = scan_fpga_inventory(fablib)
    save_results_json(records, INVENTORY_JSON)
    print_inventory_summary(records)
    assert records, 'no FPGA of any model is advertised anywhere in the resource graph'


def test_fpga_vm_launch(fablib):
    if not LAUNCH_ENABLED:
        pytest.skip('FPGA VM launch probe is opt in; set FPGA_SCAN_LAUNCH=TRUE to run it')
    records = [r for r in scan_fpga_inventory(fablib) if r['verdict'] == 'AVAILABLE']
    assert records, 'no worker has both a free FPGA and room for a minimal VM'

    results = {}
    for record in records[:LAUNCH_MAX_HOSTS]:
        results[record['host']] = launch_probe(fablib, record)
    save_results_json(results, LAUNCH_JSON)

    print('TEST SUMMARY==========================================================================================')
    for host, outcome in results.items():
        print(f"{host}: {'PASS' if outcome['state'] else outcome['error']}")
    failed = [host for host, outcome in results.items() if not outcome['state']]
    assert not failed, f"FPGA VM launch failed on: {', '.join(failed)}"


def fpga_scan():
    """Inventory scan outside pytest: python -m tests.daily.test_fpga_scan"""
    manager = FablibManager(fabric_rc=fabric_rc)
    records = scan_fpga_inventory(manager)
    save_results_json(records, INVENTORY_JSON)
    print_inventory_summary(records)
    return records


if __name__ == '__main__':
    fpga_scan()
