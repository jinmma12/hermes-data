#!/usr/bin/env python3
"""CSV ↔ JSON converter plugin — NiFi ConvertRecord equivalent."""
import csv
import io
import json
import sys


def main():
    config_msg = json.loads(sys.stdin.readline())
    config = json.loads(config_msg["data"]["config"]) if isinstance(config_msg["data"]["config"], str) else config_msg["data"]["config"]

    exec_msg = json.loads(sys.stdin.readline())
    input_data = exec_msg.get("data", {}).get("input", "")

    direction = config.get("direction", "csv_to_json")
    delimiter = config.get("delimiter", ",")
    has_header = config.get("has_header", True)

    if direction == "csv_to_json":
        if isinstance(input_data, str):
            reader = csv.reader(io.StringIO(input_data), delimiter=delimiter)
            rows = list(reader)
        else:
            rows = input_data if isinstance(input_data, list) else []

        if has_header and len(rows) > 1:
            headers = rows[0]
            records = [dict(zip(headers, row)) for row in rows[1:]]
        else:
            records = [{"col_" + str(i): v for i, v in enumerate(row)} for row in rows]

        print(json.dumps({"type": "OUTPUT", "data": records}))
        print(json.dumps({"type": "DONE", "data": {"summary": {"direction": "csv_to_json", "records": len(records)}}}))

    elif direction == "json_to_csv":
        records = input_data if isinstance(input_data, list) else [input_data]
        if not records:
            print(json.dumps({"type": "OUTPUT", "data": ""}))
            print(json.dumps({"type": "DONE", "data": {"summary": {"records": 0}}}))
            return

        output = io.StringIO()
        if has_header:
            headers = list(records[0].keys()) if isinstance(records[0], dict) else []
            writer = csv.DictWriter(output, fieldnames=headers, delimiter=delimiter)
            writer.writeheader()
            for record in records:
                writer.writerow(record if isinstance(record, dict) else {})
        else:
            writer = csv.writer(output, delimiter=delimiter)
            for record in records:
                writer.writerow(record.values() if isinstance(record, dict) else [record])

        print(json.dumps({"type": "OUTPUT", "data": output.getvalue()}))
        print(json.dumps({"type": "DONE", "data": {"summary": {"direction": "json_to_csv", "records": len(records)}}}))


if __name__ == "__main__":
    main()
