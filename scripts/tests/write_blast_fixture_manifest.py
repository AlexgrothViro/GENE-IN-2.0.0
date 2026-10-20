"""Record the indexes just built by a real-tool test; never used in production."""
import hashlib
import json
import sys
from pathlib import Path

prefix = Path(sys.argv[1])
files = {p.name: {'size': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
         for p in sorted(prefix.parent.glob(prefix.name + '.n*')) if p.is_file()}
assert files
Path(str(prefix) + '.db-manifest.json').write_text(json.dumps({'schema_version': '1.0', 'produced_files': files}, indent=2) + '\n')
