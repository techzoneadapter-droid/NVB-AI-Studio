"""Patch documented invalid duplicate TOML and bind upstream to loopback.

The version of sub2gen pinned by our installer contains duplicate
generation_routing.allowed_credential_kinds in setting_example.toml.
Use an exact-match patch rather than silently importing a modified fork.
"""
from pathlib import Path
import tomllib

path = Path("upstream-sub2gen/config/setting_example.toml")
raw = path.read_text(encoding="utf-8")
duplicate = 'allowed_credential_kinds = ["session_token", "browser_session", "oauth"]'
if raw.count("allowed_credential_kinds = ") != 2 or raw.count(duplicate) != 1:
    raise SystemExit("Unexpected upstream config; review before packaging.")
raw = raw.replace(duplicate + "\n", "")
if 'host = "0.0.0.0"' not in raw:
    raise SystemExit("Unexpected server host configuration.")
raw = raw.replace('host = "0.0.0.0"', 'host = "127.0.0.1"')
raw = raw.replace("log_requests = true", "log_requests = false")
raw = raw.replace("log_responses = true", "log_responses = false")
tomllib.loads(raw)
path.write_text(raw, encoding="utf-8")
print("Patched invalid upstream TOML and restricted engine to loopback.")
