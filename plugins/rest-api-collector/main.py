#!/usr/bin/env python3
"""REST API Collector plugin for Hermes."""
import json
import sys
import urllib.request

def main():
    # Read CONFIGURE
    config_line = sys.stdin.readline()
    config_msg = json.loads(config_line)
    config = json.loads(config_msg["data"]["config"]) if isinstance(config_msg["data"]["config"], str) else config_msg["data"]["config"]

    # Read EXECUTE
    exec_line = sys.stdin.readline()

    url = config.get("url", "")
    method = config.get("method", "GET")
    headers = config.get("headers", {})
    timeout = config.get("timeout_seconds", 30)

    try:
        req = urllib.request.Request(url, method=method)
        for k, v in headers.items():
            req.add_header(k, v)

        auth_type = config.get("auth_type", "none")
        if auth_type == "bearer":
            req.add_header("Authorization", f"Bearer {config.get('auth_token', '')}")

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            status = resp.status

        # Send OUTPUT
        print(json.dumps({"type": "OUTPUT", "data": {"response": body, "status_code": status}}))
        # Send DONE
        print(json.dumps({"type": "DONE", "data": {"summary": {"status_code": status, "bytes": len(body)}}}))
    except Exception as e:
        print(json.dumps({"type": "ERROR", "data": {"message": str(e), "code": "HTTP_ERROR"}}))
        print(json.dumps({"type": "DONE", "data": {"summary": {"error": str(e)}}}))

if __name__ == "__main__":
    main()
