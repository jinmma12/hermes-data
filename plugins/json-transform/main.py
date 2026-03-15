#!/usr/bin/env python3
"""JSON Transform plugin — NiFi JoltTransformJSON equivalent.
Supports: select fields, rename fields, add fields, remove fields, JMESPath.
"""
import json
import sys


def main():
    config_msg = json.loads(sys.stdin.readline())
    config = json.loads(config_msg["data"]["config"]) if isinstance(config_msg["data"]["config"], str) else config_msg["data"]["config"]

    exec_msg = json.loads(sys.stdin.readline())
    input_data = exec_msg.get("data", {}).get("input")
    if isinstance(input_data, str):
        input_data = json.loads(input_data)

    operation = config.get("operation", "select")
    records = input_data if isinstance(input_data, list) else [input_data] if input_data else []
    results = []

    for record in records:
        if not isinstance(record, dict):
            results.append(record)
            continue

        if operation == "select":
            fields = config.get("fields", {})
            results.append({k: record.get(k) for k in fields if k in record})

        elif operation == "rename":
            mapping = config.get("fields", {})
            renamed = {}
            for k, v in record.items():
                renamed[mapping.get(k, k)] = v
            results.append(renamed)

        elif operation == "add":
            added = dict(record)
            for k, v in config.get("fields", {}).items():
                added[k] = v
            results.append(added)

        elif operation == "remove":
            remove_list = config.get("remove_fields", [])
            results.append({k: v for k, v in record.items() if k not in remove_list})

        elif operation == "jmespath":
            try:
                import jmespath
                expr = config.get("expression", "@")
                results.append(jmespath.search(expr, record))
            except ImportError:
                results.append(record)
        else:
            results.append(record)

    output = results if isinstance(input_data, list) else results[0] if results else {}
    print(json.dumps({"type": "OUTPUT", "data": output}))
    print(json.dumps({"type": "DONE", "data": {"summary": {"operation": operation, "records_processed": len(records)}}}))


if __name__ == "__main__":
    main()
