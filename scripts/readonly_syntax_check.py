"""Syntax-check Canopy Python sources without generating pyc or modifying the checkout."""
import argparse
import ast
from pathlib import Path
import sys

DIRECTORIES = ("canopy", "tests", "scripts")


def validate_sources(root):
    root = Path(root).resolve()
    checked = 0
    errors = []
    for directory in DIRECTORIES:
        base = root / directory
        if not base.is_dir():
            errors.append(f"Missing required directory: {directory}")
            continue
        for path in sorted(base.rglob("*.py")):
            if path.is_symlink() or not path.resolve().is_relative_to(base.resolve()):
                errors.append(f"Unsafe source path: {path.relative_to(root)}")
                continue
            try:
                ast.parse(path.read_bytes(), filename=str(path))
                checked += 1
            except (SyntaxError, UnicodeError, ValueError, OSError) as error:
                errors.append(f"{path.relative_to(root)}: {error}")
    if checked == 0:
        errors.append("No Python sources found")
    return {"status": "PASS" if not errors else "FAIL", "checked": checked, "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Python AST syntax gate")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    result = validate_sources(args.root)
    print(f"Syntax: {result['status']} ({result['checked']} files)")
    for error in result["errors"]:
        print(error, file=sys.stderr)
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
