#!/usr/bin/env bash
# Print the latest Ferdium release as YAML for roles/applications/defaults/main.yml.
# Checksums are the SHA-256 digests GitHub reports for the release assets.
# Review the release notes before updating:
#   https://github.com/ferdium/ferdium-app/releases
set -euo pipefail
curl -fsS https://api.github.com/repos/ferdium/ferdium-app/releases/latest |
python3 -I -c '
import json, sys
release = json.load(sys.stdin)
version = release["tag_name"].lstrip("v")
digests = {a["name"]: (a.get("digest") or "").removeprefix("sha256:") for a in release["assets"]}
print(f"applications_ferdium_version: \"{version}\"")
print("applications_ferdium_sha256:")
for arch in ("amd64", "arm64"):
    digest = digests.get(f"Ferdium-linux-{version}-{arch}.deb")
    if not digest:
        sys.exit(f"No {arch} .deb digest found for {version}")
    print(f"  {arch}: {digest}")
'
