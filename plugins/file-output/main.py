#!/usr/bin/env python3
"""File Output transfer plugin for Hermes."""
import json
import os
import sys
import time

def main():
    config_line = sys.stdin.readline()
    config_msg = json.loads(config_line)
    config = json.loads(config_msg["data"]["config"]) if isinstance(config_msg["data"]["config"], str) else config_msg["data"]["config"]

    exec_line = sys.stdin.readline()
    exec_msg = json.loads(exec_line)
    input_data = exec_msg.get("data", {}).get("input")

    output_dir = config.get("output_dir", "/tmp/hermes-output")
    fmt = config.get("format", "json")
    template = config.get("filename_template", "output_{timestamp}.{format}")

    os.makedirs(output_dir, exist_ok=True)

    filename = template.replace("{timestamp}", str(int(time.time()))).replace("{format}", fmt)
    filepath = os.path.join(output_dir, filename)

    with open(filepath, "w") as f:
        if fmt == "json":
            json.dump(input_data, f, indent=2)
        else:
            f.write(str(input_data))

    print(json.dumps({"type": "LOG", "data": {"level": "INFO", "message": f"Written to {filepath}"}}))
    print(json.dumps({"type": "OUTPUT", "data": {"path": filepath, "size": os.path.getsize(filepath)}}))
    print(json.dumps({"type": "DONE", "data": {"summary": {"file": filepath, "format": fmt}}}))

if __name__ == "__main__":
    main()
