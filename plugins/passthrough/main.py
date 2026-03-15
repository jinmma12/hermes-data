#!/usr/bin/env python3
"""Passthrough algorithm plugin for Hermes."""
import json
import sys

def main():
    config_line = sys.stdin.readline()
    config_msg = json.loads(config_line)
    config = json.loads(config_msg["data"]["config"]) if isinstance(config_msg["data"]["config"], str) else config_msg["data"]["config"]

    exec_line = sys.stdin.readline()
    exec_msg = json.loads(exec_line)
    input_data = exec_msg.get("data", {}).get("input")

    if config.get("log_data", False):
        print(json.dumps({"type": "LOG", "data": {"level": "INFO", "message": f"Passthrough data: {input_data}"}}))

    print(json.dumps({"type": "OUTPUT", "data": input_data if input_data else {}}))
    print(json.dumps({"type": "DONE", "data": {"summary": {"passthrough": True}}}))

if __name__ == "__main__":
    main()
