"""Read-only audit of Canopy's stacked draft PR dependencies.

This tool never merges, retargets, closes, or pushes any branch.
"""
import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen


API = "https://api.github.com/repos/DevTunaSoft/Canopy/pulls?state=open&per_page=100"


def load_open_prs(*, opener=urlopen):
    request = Request(API, headers={"Accept": "application/vnd.github+json",
                                    "User-Agent": "Canopy-PR-Dependency-Audit"})
    with opener(request, timeout=15) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("GitHub response exceeded safe bound")
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, list) or len(data) >= 100:
        raise ValueError("Incomplete GitHub PR listing; explicit pagination required")
    return data


def audit(prs):
    if not isinstance(prs, list):
        raise ValueError("Expected a list of pull requests")
    branches = {}
    numbers = set()
    entries = []
    for entry in prs:
        if not isinstance(entry, dict):
            raise ValueError("Malformed PR data")
        number = entry.get("number")
        head = entry.get("head")
        base = entry.get("base")
        if type(number) is not int or number <= 0 or number in numbers:
            raise ValueError("Invalid or duplicated pull request number")
        if not isinstance(head, dict) or not isinstance(base, dict):
            raise ValueError("Missing PR refs")
        head_ref, base_ref = head.get("ref"), base.get("ref")
        if not all(isinstance(x, str) and x.strip() for x in (head_ref, base_ref)):
            raise ValueError("Invalid branch reference")
        if head_ref == base_ref or head_ref in branches:
            raise ValueError("Duplicate or self-referential head branch")
        numbers.add(number)
        branches[head_ref] = number
        entries.append({"number": number, "head": head_ref, "base": base_ref,
                        "draft": entry.get("draft") is True})

    by_number = {item["number"]: item for item in entries}
    for item in entries:
        visited = {item["number"]}
        dependencies = []
        parent_ref = item["base"]
        while parent_ref in branches:
            parent = branches[parent_ref]
            if parent in visited:
                raise ValueError("PR base-reference cycle detected")
            visited.add(parent)
            dependencies.append(parent)
            parent_ref = by_number[parent]["base"]
        item["dependencies_nearest_first"] = dependencies
        item["root_base"] = parent_ref
        item["integration_status"] = ("REVIEW" if parent_ref == "main"
                                      else "BLOCKED_UNKNOWN_BASE")
    entries.sort(key=lambda x: (len(x["dependencies_nearest_first"]), x["number"]))
    warnings = []
    roots = [entry for entry in entries if entry["root_base"] == "main"
             and not entry["dependencies_nearest_first"]]
    if len(roots) > 1:
        warnings.append("Multiple independent PR roots target main; inspect patch overlap and ancestry before any integration")
    if any(not entry["draft"] for entry in entries):
        warnings.append("Some PRs are not draft; verify authorization and review status")
    if any(entry["integration_status"] != "REVIEW" for entry in entries):
        warnings.append("Unknown/non-main base branches require manual review")
    return {"schema_version": 1, "merge_performed": False,
            "open_pr_count": len(entries), "roots": [entry["number"] for entry in roots],
            "warnings": warnings, "prs": entries,
            "note": "Branch-base graph only: not proof of clean merges, CI, commit ancestry or independent diffs"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Canopy PR dependency audit")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--input", type=Path, help="Saved GitHub pull request API JSON")
    group.add_argument("--live", action="store_true", help="Read public GitHub PR metadata")
    parser.add_argument("--output", type=Path, default=Path("test-results/pr-stack-audit.json"))
    args = parser.parse_args(argv)
    try:
        data = load_open_prs() if args.live else json.loads(args.input.read_text(encoding="utf-8"))
        result = audit(data)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, UnicodeError) as error:
        parser.exit(1, f"BLOCKED: {error}\n")
    print(f"Audited {result['open_pr_count']} open PRs without modifying GitHub")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
