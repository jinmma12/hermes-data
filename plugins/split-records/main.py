#!/usr/bin/env python3
"""Split records plugin — NiFi SplitText/SplitJson equivalent."""
import json
import sys


def main():
    config_msg = json.loads(sys.stdin.readline())
    config = json.loads(config_msg["data"]["config"]) if isinstance(config_msg["data"]["config"], str) else config_msg["data"]["config"]

    exec_msg = json.loads(sys.stdin.readline())
    input_data = exec_msg.get("data", {}).get("input")
    if isinstance(input_data, str):
        input_data = json.loads(input_data)

    batch_size = config.get("batch_size", 1)
    split_field = config.get("split_field")

    records = []
    if isinstance(input_data, list):
        records = input_data
    elif isinstance(input_data, dict) and split_field and split_field in input_data:
        field_data = input_data[split_field]
        if isinstance(field_data, list):
            records = field_data
        else:
            records = [input_data]
    elif input_data:
        records = [input_data]

    # Split into batches
    batches = []
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        batches.append(batch if len(batch) > 1 else batch[0])

    for batch in batches:
        print(json.dumps({"type": "OUTPUT", "data": batch}))

    print(json.dumps({"type": "DONE", "data": {"summary": {
        "input_records": len(records),
        "batches": len(batches),
        "batch_size": batch_size
    }}}))


if __name__ == "__main__":
    main()
