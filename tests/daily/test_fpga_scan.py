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
    FPGA_SCAN_SUBMIT_TIMEOUT   seconds to wait for a probe slice, default 1800
    FPGA_SCAN_DELETE_RETRIES   delete attempts per slice, default 10
    FPGA_SCAN_SHELL_CACHE_DAYS age at which a shell reading is stale, default 30
"""

import calendar
import json
import os
import re
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

# Vendor ids used to label lspci output.
PCI_VENDORS = {'10ee': 'Xilinx/AMD', '1172': 'Altera/Intel'}

# What a card currently carries is decided by its PCI device id, and reading it
# is cheap. This names the shell and the driver that binds that state; it is not
# a usability grade, because whether a card is usable depends on the runtime a
# given experiment brings. An id absent from this table is reported verbatim as
# unrecognised rather than guessed at or silently dropped.
SHELL_IDS = {
    '10ee:903f': ('network-shell', 'OpenNIC / ESnet network shell', 'xdma (dma_ip_drivers)'),
    '10ee:913f': ('network-shell', 'ESnet SmartNIC second PF', 'xdma (dma_ip_drivers)'),
    '10ee:d00c': ('golden', 'Alveo golden (factory/recovery) image', 'management only'),
    '10ee:500c': ('xrt-xdma', 'xilinx_u280_gen3x16_xdma_base_1', 'xocl / XRT'),
    '10ee:500d': ('xrt-xdma', 'xilinx_u280_gen3x16_xdma_base_1 (mgmt PF)', 'xclmgmt / XRT'),
}

SHELL_HELP = {
    'xrt-xdma': 'XRT XDMA deployment shell; xocl binds it and an xclbin can load',
    'xrt-xdma-no-metadata': 'XRT shell on the bus but the UUID ROM reads 0; xocl will not probe it',
    'golden': 'factory/recovery image, management only; flash a deployment shell to use it',
    'golden-erased': 'golden with an erased version field; cannot be flashed over PCIe',
    'network-shell': 'OpenNIC/ESnet network design; XRT never binds it, xdma does',
    'unrecognised': 'a PCI function is present whose device id is not in this table',
    'none': 'no accelerator PCI function was visible inside the VM',
}

INVENTORY_JSON = 'fpga_scan.json'
LAUNCH_JSON = 'fpga_launch.json'
SHELL_CACHE_JSON = 'fpga_shell_cache.json'

# An inventory pass cannot see a shell -- that needs a VM on the worker -- so
# observations are cached and reported with their age. Older than this and the
# reading is labelled stale rather than presented as current.
SHELL_CACHE_DAYS = int(os.getenv('FPGA_SCAN_SHELL_CACHE_DAYS', '30'))
TIME_FORMAT = '%Y-%m-%dT%H:%M:%SZ'

SCAN_SITES = [s for s in os.getenv('FPGA_SCAN_SITES', '').replace(',', ' ').split() if s]
LAUNCH_ENABLED = os.getenv('FPGA_SCAN_LAUNCH', 'FALSE').upper() == 'TRUE'
LAUNCH_MAX_HOSTS = int(os.getenv('FPGA_SCAN_LAUNCH_MAX_HOSTS', '1'))
KEEP_FAILED = os.getenv('FPGA_SCAN_KEEP_FAILED', 'FALSE').upper() == 'TRUE'

# Passed to submit() explicitly rather than inherited silently: a card that
# never leaves Configuring otherwise burns fablib's full 1800s default before
# a daily job learns anything.
SUBMIT_TIMEOUT = int(os.getenv('FPGA_SCAN_SUBMIT_TIMEOUT', '1800'))
DELETE_RETRIES = int(os.getenv('FPGA_SCAN_DELETE_RETRIES', '10'))
DELETE_RETRY_WAIT = int(os.getenv('FPGA_SCAN_DELETE_RETRY_WAIT', '30'))

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
    return apply_shell_cache(records)


def collapse(exc, limit=1200):
    """One-line form of an exception, kept long enough to carry the reason.

    The useful part of a playbook or priming failure sits at the END of the
    message ("Playbook has failed tasks: ..."), so a short cap throws away
    exactly what is worth reading.
    """
    text = ' '.join(str(exc).split()) or repr(exc)
    return text[:limit]


def shell_column(record):
    """One line saying what a card carries and how current the reading is."""
    source = record.get('shell_source') or 'none'
    if source == 'none':
        return 'not observed -- needs a VM on this worker to read the card'
    age = record.get('shell_age_days')
    if age == '' or age is None:
        when = 'at an unknown time'
    elif age == 0:
        when = 'today'
    else:
        when = f'{age} day(s) ago'
    shell_class = record.get('shell_class') or 'unknown'
    name = record.get('shell_name') or ''
    label = f'{shell_class} {name}'.strip()
    ids = record.get('pci_ids') or 'no pci function'
    binds = record.get('binds_with') or 'none'
    stale = ' [STALE]' if source == 'cache-stale' else ''
    line = f'{label} [{ids}] binds_with={binds} -- observed {when}{stale}'
    note = record.get('shell_note')
    if note:
        line = f'{line}\n        note: {note}'
    # The rescan outcome explains an empty reading, so it belongs in the
    # report rather than only in the JSON.
    rescan = record.get('shell_rescan')
    if rescan and rescan != 'not needed':
        line = f'{line}\n        pci rescan: {rescan}'
    return line


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
            print(f"      shell: {shell_column(r)}")
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
    shells = {}
    for r in records:
        key = r.get('shell_class') or 'not-observed'
        shells[key] = shells.get(key, 0) + 1
    print('  BY SHELL: ' + ',  '.join(f'{k}={n}' for k, n in sorted(shells.items())))
    for key in sorted(shells):
        if key in SHELL_HELP:
            print(f"    {key:<22} {SHELL_HELP[key]}")
        else:
            print(f"    {key:<22} no VM has yet reported what this card carries")
    models = sorted({r['model'] for r in records})
    print(f"  MODELS DISCOVERED: {', '.join(models)}")


def identify_shell(facts):
    """Name the shell a card currently carries, from the PCI ids it exposes.

    Returns pci_ids, shell_class, shell_name, binds_with and a note. This
    describes the card's state and which driver claims it; it deliberately
    stops short of declaring the card good or bad.
    """
    text = '\n'.join(facts.get('accelerators') or [])
    tools = facts.get('vendor_tool') or ''
    pairs = re.findall(r'\[([0-9a-fA-F]{4}):([0-9a-fA-F]{4})\]', text)
    ids = sorted({f'{v.lower()}:{d.lower()}' for v, d in pairs
                  if v.lower() in PCI_VENDORS})
    pci_ids = ' '.join(ids)

    if not ids:
        return {'pci_ids': '', 'shell_class': 'none', 'shell_name': '',
                'binds_with': '',
                'shell_note': 'the component is advertised but no accelerator PCI '
                              'function is visible in the VM'}

    devices = {i.split(':')[1] for i in ids if i in SHELL_IDS}
    if not devices:
        return {'pci_ids': pci_ids, 'shell_class': 'unrecognised', 'shell_name': '',
                'binds_with': '',
                'shell_note': f"device id(s) {pci_ids} are not in this scan's shell table"}

    # Order matters: a card can expose an XRT PF and a management PF at once,
    # and the deployment shell is the more specific answer.
    if {'500c', '500d'} & devices:
        shell_class, shell_name, binds = SHELL_IDS['10ee:500c']
        note = ''
        # A JTAG flash writes the bitstream but not the metadata xbmgmt
        # persists, which carries the UUID ROM. The card then looks healthy on
        # the bus and xocl still refuses to probe it.
        if re.search(r'Logic UUID\s*:?\s*0x0\b', tools, re.I):
            shell_class = 'xrt-xdma-no-metadata'
            shell_name = f'{shell_name} (UUID 0)'
            binds = 'none'
            note = 'UUID ROM reads 0; not repairable with xbmgmt program --base'
        elif not tools:
            note = ('named from the PCI id alone; no vendor tool present in the VM to '
                    'confirm the UUID ROM')
        return {'pci_ids': pci_ids, 'shell_class': shell_class, 'shell_name': shell_name,
                'binds_with': binds, 'shell_note': note}

    if 'd00c' in devices:
        shell_class, shell_name, binds = SHELL_IDS['10ee:d00c']
        # An erased version field reads as 0xFFFFFFFF. Note the string
        # "Factory or Recovery image detected" appears on healthy cards too and
        # is not the signal here.
        if 'GOLDEN_4294967295' in tools:
            return {'pci_ids': pci_ids, 'shell_class': 'golden-erased',
                    'shell_name': 'GOLDEN_4294967295', 'binds_with': binds,
                    'shell_note': 'golden version field is erased; flashing over PCIe '
                                  'will fail and the card needs staff intervention'}
        return {'pci_ids': pci_ids, 'shell_class': shell_class, 'shell_name': shell_name,
                'binds_with': binds,
                'shell_note': 'flash a deployment shell to make the card loadable'}

    if {'903f', '913f'} & devices:
        # Function count separates the two network designs. A lone 903f is a
        # healthy OpenNIC card, not a half-restored one.
        if {'903f', '913f'} <= devices:
            shell_name = 'ESnet SmartNIC (903f + 913f)'
            note = 'two PFs means the ESnet SmartNIC design'
        else:
            shell_name = 'OpenNIC (903f)'
            note = 'a lone 903f is a healthy OpenNIC card, not a half-restored one'
        return {'pci_ids': pci_ids, 'shell_class': 'network-shell', 'shell_name': shell_name,
                'binds_with': SHELL_IDS['10ee:903f'][2], 'shell_note': note}

    return {'pci_ids': pci_ids, 'shell_class': 'unrecognised', 'shell_name': '',
            'binds_with': '',
            'shell_note': f"device id(s) {pci_ids} are not in this scan's shell table"}


def cache_key(record):
    return f"{record['site']}/{record['host']}/{record['model']}"


def read_shell_cache():
    try:
        with open(SHELL_CACHE_JSON) as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


def record_shell_observation(record, shell):
    """Persist one shell reading so later inventory passes can report it."""
    cache = read_shell_cache()
    entry = dict(shell)
    entry['observed_at'] = time.strftime(TIME_FORMAT, time.gmtime())
    cache[cache_key(record)] = entry
    with open(SHELL_CACHE_JSON, 'w') as handle:
        json.dump(cache, handle, indent=2, sort_keys=True)
    return entry


def shell_age_days(observed_at):
    """Whole days since an observation, or '' if the stamp is unreadable."""
    try:
        stamp = calendar.timegm(time.strptime(observed_at, TIME_FORMAT))
    except (TypeError, ValueError):
        return ''
    return max(0, int((time.time() - stamp) // 86400))


def apply_shell_cache(records):
    """Carry the last observed shell into an inventory report.

    An inventory pass cannot see a shell: it is only visible from inside a VM
    on that worker. So each record reports the most recent reading and its age,
    and a card that has never been probed says so rather than being guessed at.
    """
    cache = read_shell_cache()
    for record in records:
        entry = cache.get(cache_key(record))
        if not entry:
            record.update({
                'shell_source': 'none', 'shell_class': '', 'shell_name': '',
                'binds_with': '', 'pci_ids': '', 'shell_observed_at': '',
                'shell_age_days': '', 'shell_rescan': '',
                'shell_note': 'shell never observed; run with FPGA_SCAN_LAUNCH=TRUE '
                              'to find out what this card carries',
            })
            continue
        age = shell_age_days(entry.get('observed_at', ''))
        stale = age == '' or age > SHELL_CACHE_DAYS
        note = entry.get('shell_note', '')
        if stale:
            detail = (f'observation is {age} day(s) old' if age != ''
                      else 'observation timestamp could not be read')
            note = (note + ' | ' if note else '') + detail
        record.update({
            'shell_source': 'cache-stale' if stale else 'cache',
            'shell_class': entry.get('shell_class', ''),
            'shell_name': entry.get('shell_name', ''),
            'binds_with': entry.get('binds_with', ''),
            'pci_ids': entry.get('pci_ids', ''),
            'shell_observed_at': entry.get('observed_at', ''),
            'shell_age_days': age,
            'shell_note': note,
            'shell_rescan': entry.get('rescan', ''),
        })
    return records


def read_card_state(node, component_name='fpga1'):
    """Read the card, rescanning the PCI bus once if nothing shows up.

    An attached FPGA frequently does not appear on the guest's PCI bus until a
    rescan, so reporting it absent on the first empty lspci calls a card
    missing when it is merely not yet enumerated. The rescan is deliberately
    tied to an empty result and to no other condition.
    """
    facts = probe_card(node)
    if facts['accelerators']:
        return facts
    try:
        node.rescan_pci(component_name=component_name)
    except Exception as e:
        facts['rescan'] = f'rescan unavailable: {collapse(e)}'
        return facts
    second = probe_card(node)
    if second['accelerators']:
        second['rescan'] = 'card appeared only after a PCI rescan'
        return second
    second['rescan'] = 'rescan completed and the card is still absent'
    return second


def probe_card(node):
    """Collect what the VM can see about its FPGA, without judging it.

    Descriptive on purpose: device ids, classes and bound drivers are reported
    verbatim rather than graded, because whether a card is usable depends on
    the runtime a given experiment brings with it.
    """
    facts = {'rescan': 'not needed'}
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
    tools = (stdout or '').strip()
    # xbmgmt is what reports an erased golden version field.
    stdout, _stderr = node.execute(
        'command -v xbmgmt >/dev/null && sudo xbmgmt examine 2>&1 || true', quiet=True)
    facts['vendor_tool'] = (tools + '\n' + (stdout or '').strip()).strip()[:6000]
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
    # A slice that never left Configuring cannot be deleted yet -- the
    # orchestrator answers "Unable to delete Slices that are not yet stable,
    # try again later" -- so one attempt is not enough. Giving up here leaks a
    # slice holding one of very few cards, which is the thing this function
    # exists to prevent.
    print(f"[{slice_name}] deleting probe slice and releasing the card")
    for attempt in range(1, DELETE_RETRIES + 1):
        try:
            slice_obj.delete()
            print(f"[{slice_name}] deleted")
            return
        except Exception as e:
            print(f"[{slice_name}] delete attempt {attempt}/{DELETE_RETRIES} "
                  f"failed: {collapse(e)}")
            if attempt < DELETE_RETRIES:
                time.sleep(DELETE_RETRY_WAIT)
    print(f"[{slice_name}] STILL NOT DELETED after {DELETE_RETRIES} attempts -- "
          f"this slice may be holding an FPGA; delete it by hand")


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
        slice_obj.submit(wait_timeout=SUBMIT_TIMEOUT)
        slice_obj.update()
        state = str(slice_obj.get_state())
        if state != 'StableOK':
            return {'state': False, 'launched': False,
                    'error': f"slice state {state}: {error_message(slice_obj=slice_obj)}",
                    'slice_id': slice_id(slice_obj, slice_name),
                    'shell': {}, 'card': {}}
        placed = True
        slice_obj.wait_ssh(progress=False)
        # Handles built before submit() are stale descriptors; the live ones
        # only exist after re-fetching the slice.
        slice_obj = fablib.get_slice(name=slice_name)
        node = slice_obj.get_node(name=PROBE_NODE)
        card = read_card_state(node)
        shell = identify_shell(card)
        shell['rescan'] = card.get('rescan', '')
        record_shell_observation(record, shell)
        print(f"[{short_host}] VM launched; {len(card['accelerators'])} accelerator "
              f"function(s) visible")
        if shell['rescan'] and shell['rescan'] != 'not needed':
            print(f"[{short_host}] pci rescan: {shell['rescan']}")
        print(f"[{short_host}] shell: {shell['shell_class']} "
              f"{shell['shell_name']} [{shell['pci_ids'] or 'no pci function'}] "
              f"binds_with={shell['binds_with'] or 'none'}")
        if shell['shell_note']:
            print(f"[{short_host}] note: {shell['shell_note']}")
        return {'state': True, 'launched': True, 'error': '',
                'slice_id': slice_id(slice_obj, slice_name),
                'shell': shell, 'card': card}
    except Exception as e:
        print(f"[{short_host}] {'probe' if placed else 'launch'} failed: {e}")
        traceback.print_exc()
        message = error_message(slice_obj=slice_obj, exception=e) if slice_obj else str(e)
        return {'state': False, 'launched': placed, 'error': message,
                'slice_id': slice_id(slice_obj, slice_name) if slice_obj else slice_name,
                'shell': {}, 'card': {}}
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
