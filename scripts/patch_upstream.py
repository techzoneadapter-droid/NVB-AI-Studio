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

# Upstream imports these providers during startup but classifies them as dev-only.
# Promote them into production dependencies; CI re-locks the pinned workspace.
project = Path("upstream-sub2gen/pyproject.toml")
original = project.read_text(encoding="utf-8")
runtime, boundary, dev = original.partition("[dependency-groups]")
if not boundary:
    raise SystemExit("Upstream metadata changed; inspect manually.")
anchor = '  "sub2gen-worker-protocol",\n]'
if runtime.count(anchor) != 1:
    raise SystemExit("Unexpected runtime dependency marker.")
for name in ("sub2gen-provider-chatgpt", "sub2gen-image-worker"):
    line = '  "' + name + '",\n'
    if dev.count(line) != 1:
        raise SystemExit("Missing expected development dependency: " + name)
    dev = dev.replace(line, "", 1)
runtime = runtime.replace(anchor,
    '  "sub2gen-worker-protocol",\n  "sub2gen-provider-chatgpt",\n  "sub2gen-image-worker",\n]', 1)
updated = runtime + boundary + dev
metadata = tomllib.loads(updated)
for name in ("sub2gen-provider-chatgpt", "sub2gen-image-worker"):
    assert name in metadata["project"]["dependencies"]
    assert name not in metadata["dependency-groups"]["dev"]
project.write_text(updated, encoding="utf-8")
print("Bundled production dependencies now include eager-import providers.")
