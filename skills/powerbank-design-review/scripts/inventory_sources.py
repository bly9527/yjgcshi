#!/usr/bin/env python3
"""Index local design sources without interpreting or modifying their contents.

Requires Python 3.9+. Explicit input files are indexed regardless of extension;
--extensions filters files discovered under directories. Hashes are read twice
and stat signatures checked to flag files changing during the observation.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from datetime import datetime, timezone


DEFAULT_EXTENSIONS = ".schdoc,.pcbdoc,.pdf,.xlsx,.xls,.zip,.7z,.epro,.eprj,.esch,.epcb"
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}


def is_link(path):
    info = path.lstat()
    # Cloud placeholders also use reparse points; skip only redirecting links.
    return stat.S_ISLNK(info.st_mode) or getattr(info, "st_reparse_tag", 0) in {
        0xA0000003, 0xA000000C  # Windows mount-point/junction and symlink tags
    }


def signature(info):
    return (info.st_size, info.st_mtime_ns, info.st_ctime_ns, info.st_dev, info.st_ino)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_file(path):
    if is_link(path):
        return None, {"path": str(path), "error": "source_became_symlink_or_junction"}
    before = path.stat()
    first = sha256(path)
    middle = path.stat()
    second = sha256(path)
    after = path.stat()
    observation = {
        "bytes_before": before.st_size, "bytes_after": after.st_size,
        "mtime_ns_before": before.st_mtime_ns, "mtime_ns_after": after.st_mtime_ns,
        "sha256_first": first, "sha256_second": second,
    }
    if signature(before) != signature(middle) or signature(middle) != signature(after) or first != second:
        return None, {"path": str(path), "error": "source_changed_during_read", **observation}
    return {
        "path": str(path), "name": path.name, "bytes": after.st_size,
        "mtime": datetime.fromtimestamp(after.st_mtime, timezone.utc).isoformat(),
        "mtime_ns": after.st_mtime_ns, "sha256": second,
        "coverage": "indexed_only", "read_observation": observation,
    }, None


def discover(roots, extensions, errors, skipped):
    found = {}
    stack = [(Path(os.path.abspath(root)), True) for root in roots]
    visited_dirs = set()
    while stack:
        path, explicit = stack.pop()
        try:
            if is_link(path):
                skipped.append({"path": str(path), "reason": "symlink_or_reparse_point"})
                continue
            if path.is_dir():
                if path.name.casefold() in SKIP_DIRS:
                    skipped.append({"path": str(path), "reason": "excluded_directory"})
                    continue
                resolved = path.resolve()
                if resolved in visited_dirs:
                    continue
                visited_dirs.add(resolved)
                stack.extend((child, False) for child in path.iterdir())
            elif path.is_file() and (explicit or path.suffix.casefold() in extensions):
                resolved = path.resolve()
                found[resolved] = resolved
        except OSError as error:
            errors.append({"path": str(path), "error": type(error).__name__, "message": str(error)})
    return sorted(found.values(), key=lambda p: str(p).casefold())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("roots", nargs="+", help="Input directories or explicit files (read-only)")
    parser.add_argument("--output", required=True, help="JSON manifest path; cannot be an input source")
    parser.add_argument("--extensions", default=DEFAULT_EXTENSIONS, help="Comma-separated directory-scan extensions")
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output manifest, never an input source")
    args = parser.parse_args(argv)
    extensions = {"." + item.strip().lstrip(".").casefold() for item in args.extensions.split(",") if item.strip()}
    output = Path(os.path.abspath(args.output))
    errors, skipped = [], []
    files = discover(args.roots, extensions, errors, skipped)
    try:
        if output.is_symlink() or (output.exists() and is_link(output)):
            raise ValueError("Output must not be a symlink or reparse point")
        resolved_output = output.resolve()
        explicit_inputs = {Path(root).resolve() for root in args.roots}
        if resolved_output in explicit_inputs or resolved_output in set(files):
            raise ValueError("Output collides with an input source")
        # A hard link can have a different path but still designate the same source.
        if output.exists() and any(os.path.samefile(output, path) for path in files):
            raise ValueError("Output is a hard link to an input source")
        if output.exists() and not args.overwrite:
            raise ValueError("Output already exists; use --overwrite only for an output manifest")
        if output.exists() and not output.is_file():
            raise ValueError("Output is not a regular file")
        if output.exists() and args.overwrite:
            try:
                previous = json.loads(output.read_text(encoding="utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                raise ValueError("Refusing to overwrite a file that is not an inventory manifest") from None
            if not isinstance(previous, dict) or previous.get("tool") != "powerbank-design-review.inventory_sources":
                raise ValueError("--overwrite only replaces manifests generated by this script")
    except (OSError, ValueError) as error:
        print(json.dumps({"errors": [{"path": str(output), "error": str(error)}]}, ensure_ascii=False), file=sys.stderr)
        return 2
    records = []
    for path in files:
        try:
            record, error = inspect_file(path)
            if error:
                errors.append(error)
            else:
                records.append(record)
        except OSError as error:
            errors.append({"path": str(path), "error": type(error).__name__, "message": str(error)})
    hashes, names = {}, {}
    for record in records:
        hashes.setdefault(record["sha256"], []).append(record["path"])
        names.setdefault(record["name"].casefold(), []).append(record)
    manifest = {
        "schema_version": 1, "tool": "powerbank-design-review.inventory_sources",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "roots": [str(Path(root).absolute()) for root in args.roots],
        "scope": "Directory suffix filtering; explicit files accepted regardless of suffix. Archives indexed, not unpacked.",
        "coverage_note": "Hashes and file metadata only; no schematic, PCB, PDF or workbook content interpretation.",
        "files": records,
        "duplicate_sha256_groups": [{"sha256": key, "paths": paths} for key, paths in sorted(hashes.items()) if len(paths) > 1],
        "same_name_different_content": [{"name_casefold": key, "files": [{"path": r["path"], "sha256": r["sha256"]} for r in group]} for key, group in sorted(names.items()) if len({r["sha256"] for r in group}) > 1],
        "skipped": sorted(skipped, key=lambda r: r["path"].casefold()), "errors": errors,
    }
    encoded = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    temporary = None
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        if args.overwrite:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, prefix=".inventory-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(encoded)
            os.replace(temporary, output)
        else:
            with output.open("x", encoding="utf-8") as stream:
                stream.write(encoded)
    except OSError as error:
        print(json.dumps({"errors": [{"path": str(output), "error": str(error)}]}, ensure_ascii=False), file=sys.stderr)
        return 2
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print(json.dumps({"output": str(output), "indexed": len(records), "errors": len(errors), "coverage": "indexed_only"}, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
