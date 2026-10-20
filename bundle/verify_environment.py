"""Check required Conda archive identities before using an existing prefix."""
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit, unquote

prefix, lock = map(Path, sys.argv[1:])
installed = {}
for path in (prefix / "conda-meta").glob("*.json"):
    record = json.loads(path.read_text())
    filename = record.get("fn") or unquote(urlsplit(record.get("url", "")).path.rsplit("/", 1)[-1])
    installed[filename] = record
errors = []
required = 0
for line in lock.read_text().splitlines():
    if not line.startswith("https://"):
        continue
    required += 1
    url = urlsplit(line)
    filename = unquote(url.path.rsplit("/", 1)[-1])
    record = installed.get(filename)
    if record is None:
        errors.append("Missing or different build: " + filename)
    elif url.fragment and record.get("md5") != url.fragment:
        errors.append("Archive checksum differs: " + filename)
if required == 0:
    errors.append("Lock contains no package URLs.")
if errors:
    print("\n".join(errors), file=sys.stderr)
    sys.exit("Existing environment differs from the recorded lock. Set GENEIN_BUNDLE_DIR to a new directory and install there.")
print(f"Verified {required} required Conda archive identities; additional packages are permitted.")
