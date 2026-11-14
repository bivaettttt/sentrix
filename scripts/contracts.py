import json
import subprocess
import sys
from pathlib import Path
from re import compile as pattern

from sentrix.api import app

target = Path("docs/openapi.json")
desired = json.dumps(app.openapi(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
if "--write" in sys.argv:
    target.write_text(desired)
else:
    assert target.read_text() == desired, "OpenAPI drift"
    sensitive = pattern(
        rb"gh[pous]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    )
    links = pattern(r"\]\(([^)]+)\)")
    for name in subprocess.check_output(["git", "ls-files", "-z"]).decode().split("\0"):
        if not name:
            continue
        path = Path(name)
        contents = path.read_bytes()
        assert path.name != ".env" and not sensitive.search(contents), (
            f"Possible secret in {path}"
        )
        if path.suffix == ".md":
            for raw in links.findall(contents.decode()):
                relative = raw.split("#", 1)[0]
                assert (
                    not relative
                    or "://" in relative
                    or (path.parent / relative).is_file()
                ), (path, relative)
