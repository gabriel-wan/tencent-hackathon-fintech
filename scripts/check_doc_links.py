"""Report Markdown links that point to a file or folder that doesn't exist.

Run from the repository root:  python3 scripts/check_doc_links.py
Exits with 1 if any link is broken, so it can also run in CI. Web links (http, https, mailto)
and in-page anchors (#section) are not checked.
"""

import os
import re
import sys

SKIP_DIRS = {".git", ".claude", "node_modules", ".next", ".venv", "__pycache__"}
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")  # [text](target) or [text](target#anchor)


def markdown_files(root: str):
    for folder, subfolders, files in os.walk(root):
        subfolders[:] = [d for d in subfolders if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".md"):
                yield os.path.join(folder, name)


def main() -> int:
    broken = []
    for path in sorted(markdown_files(".")):
        with open(path, encoding="utf-8") as f:
            text = f.read()
        for target in LINK.findall(text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not os.path.exists(os.path.normpath(os.path.join(os.path.dirname(path), target))):
                broken.append(f"{os.path.relpath(path)}: {target}")
    print("\n".join(broken) if broken else "All links resolve.")
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
