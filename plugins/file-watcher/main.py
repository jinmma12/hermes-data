#!/usr/bin/env python3
"""File Watcher plugin for Hermes."""
import glob
import json
import os
import sys

def main():
    config_line = sys.stdin.readline()
    config_msg = json.loads(config_line)
    config = json.loads(config_msg["data"]["config"]) if isinstance(config_msg["data"]["config"], str) else config_msg["data"]["config"]

    exec_line = sys.stdin.readline()

    watch_path = config.get("watch_path", ".")
    pattern = config.get("pattern", "*")
    recursive = config.get("recursive", False)

    full_pattern = os.path.join(watch_path, "**", pattern) if recursive else os.path.join(watch_path, pattern)
    files = glob.glob(full_pattern, recursive=recursive)

    for f in files:
        stat = os.stat(f)
        print(json.dumps({"type": "OUTPUT", "data": {
            "path": f,
            "filename": os.path.basename(f),
            "size": stat.st_size,
            "modified": stat.st_mtime
        }}))

    print(json.dumps({"type": "DONE", "data": {"summary": {"files_found": len(files)}}}))

if __name__ == "__main__":
    main()
