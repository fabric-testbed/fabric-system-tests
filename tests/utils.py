import json
import random
from itertools import combinations

from fabrictestbed_extensions.fablib.slice import Slice


def error_message(slice_obj: Slice, exception: Exception = None):
    if exception and "Slice Exception" not in str(exception):
        return str(exception)

    cascade_notice_string1 = "Closing reservation due to failure in slice"
    cascade_notice_string2 = "is in a terminal state"

    try:
        ret_val = ""
        for sliver in slice_obj.get_slivers():
            if cascade_notice_string1 in sliver.notice or cascade_notice_string2 in sliver.notice:
                continue
            ret_val += f" {sliver.sliver_id} - {sliver.notice}"

        return ret_val
    except Exception:
        if exception:
            return str(exception)
        else:
            return "Fail"


def save_results_json(results, filename="iperf_test_results.json"):
    with open(filename, "w") as f:
        json.dump(results, f, indent=2)


def make_site_pairs(sites: list[str]):
    """
    Randomly select unique (site1, site2, worker1, worker2) pairs.

    Constraints:
    - site1 != site2
    - No duplicate pairs (e.g., both (a, b) and (b, a))
    - Each site must have at least one worker
    - Number of pairs is len(sites) // 2
    """
    # Generate all valid (site1, site2) combinations
    valid_pairs = [
        (site1, site2)
        for site1, site2 in combinations(sites, 2)
    ]

    count = len(sites) // 2
    if count > len(valid_pairs):
        raise ValueError(f"Cannot select {count} unique pairs from only {len(valid_pairs)} valid combinations.")

    return random.sample(valid_pairs, count)