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
from fabrictestbed_extensions.fablib.fablib import FablibManager
from tests.base_test import fabric_rc


# Mapping from remote credential manager host to expected sites
EXPECTED_SITES_MAP = {
    "cm.fabric-testbed.net": {
    "EDC", "NCSA", "TACC", "STAR", "MAX", "WASH", "MICH", "SALT", "DALL", "MASS",
    "UTAH", "UCSD", "CLEM", "FIU", "GPN", "CERN", "INDI", "NEWY", "KANS",
    "PSC", "ATLA", "SEAT", "LOSA", "AMST", "GATECH", "RUTG", "PRIN", "HAWI", "SRI",
    "EDUKY", "BRIST", "TOKY", "CIEN"
    },
    "beta-2.fabric-testbed.net": {"RENC", "LBNL"},  # Example test deployment
    # Add other known environments here
}

@pytest.fixture(scope="module")
def fablib():
    fablib = FablibManager(fabric_rc=fabric_rc)
    fablib.show_config()
    return fablib


def get_expected_sites(fablib):
    """
    Determine expected sites based on configured credential manager host.
    """
    cm_host = fablib.get_config().get("credmgr_host")
    if cm_host in EXPECTED_SITES_MAP:
        return EXPECTED_SITES_MAP[cm_host]
    else:
        pytest.skip(f"No expected sites defined for credmgr host: {cm_host}")


def test_list_sites_advertised(fablib):
    """
    Test that the advertised site list via CF REST API contains expected sites
    based on the configured credential manager.
    """
    try:
        site_dicts = fablib.list_sites(output="list")
        advertised_sites = {site["name"] for site in site_dicts if "name" in site}

        expected_sites = get_expected_sites(fablib)

        missing = expected_sites - advertised_sites
        assert not missing, f"Missing expected sites from REST API response: {sorted(missing)}"
    except Exception as e:
        pytest.fail(f"Failed to retrieve or validate site list: {e}")
