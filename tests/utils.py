import json

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
