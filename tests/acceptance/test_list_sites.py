import pytest
from fabrictestbed_extensions.fablib.fablib import FablibManager

fabric_rc = None
#os.environ['FABRIC_AVOID'] = 'UKY'
#fabric_rc = '/Users/kthare10/work/fabric_config_dev/fabric_rc'


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
