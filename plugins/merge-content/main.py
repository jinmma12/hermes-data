#!/usr/bin/env python3
"""Merge content plugin — NiFi MergeContent equivalent."""
import json
import sys
import time


def main():
    config_msg = json.loads(sys.stdin.readline())
    config = json.loads(config_msg["data"]["config"]) if isinstance(config_msg["data"]["config"], str) else config_msg["data"]["config"]

    exec_msg = json.loads(sys.stdin.readline())
    input_data = exec_msg.get("data", {}).get("input")
    if isinstance(input_data, str):
        input_data = json.loads(input_data)

    strategy = config.get("merge_strategy", "array")
    wrap_field = config.get("wrap_field")
    add_metadata = config.get("add_metadata", True)

    records = input_data if isinstance(input_data, list) else [input_data] if input_data else []

    if strategy == "array":
        merged = records
    elif strategy == "concat":
        # Merge all dicts into one (later keys overwrite)
        merged = {}
        for record in records:
            if isinstance(record, dict):
                merged.update(record)
    elif strategy == "zip":
        # Merge by index position
        if records and isinstance(records[0], dict):
            keys = set()
            for r in records:
                keys.update(r.keys() if isinstance(r, dict) else [])
            merged = {k: [r.get(k) for r in records if isinstance(r, dict)] for k in keys}
        else:
            merged = records
    else:
        merged = records

    if wrap_field:
        merged = {wrap_field: merged}

    if add_metadata and isinstance(merged, dict):
        merged["_merge_metadata"] = {
            "strategy": strategy,
            "input_count": len(records),
            "merged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    print(json.dumps({"type": "OUTPUT", "data": merged}))
    print(json.dumps({"type": "DONE", "data": {"summary": {
        "strategy": strategy,
        "input_records": len(records),
    }}}))


if __name__ == "__main__":
    main()
