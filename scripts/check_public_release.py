"""Check an exact Git index or commit snapshot before public publication."""
from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import struct
import subprocess
import sys
import zlib


ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(
    r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|AKIA[A-Z0-9]{16}|"
    r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----)"
)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")
PERSONAL_PATH = re.compile(r"[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]", re.I)
PRIVATE_ADDRESS = re.compile(r"\b(?:192\.168\.\d+\.\d+|10\.\d+\.\d+\.\d+|[\w-]+\.ts\.net)\b")


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=ROOT)


def noreply(email: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@users\.noreply\.github\.com|noreply@github\.com", email, re.I))


def check_text(path: str, data: bytes) -> list[str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{path}: unexpected binary file"]
    errors = []
    for name, pattern in [("possible secret", SECRET), ("personal path", PERSONAL_PATH), ("private address", PRIVATE_ADDRESS)]:
        if pattern.search(text):
            errors.append(f"{path}: {name}")
    for match in EMAIL.findall(text):
        # Reserved documentation domains are examples, never personal contacts.
        domain = match.rsplit("@", 1)[1].lower()
        if not noreply(match) and domain not in {"example.com", "example.org", "example.net"}:
            errors.append(f"{path}: unexpected email address")
            break
    return errors


def check_png(path: str, data: bytes) -> list[str]:
    try:
        assert data.startswith(b"\x89PNG\r\n\x1a\n")
        offset, kinds = 8, []
        while offset < len(data):
            size = struct.unpack(">I", data[offset:offset + 4])[0]
            kind = data[offset + 4:offset + 8]
            payload = data[offset + 8:offset + 8 + size]
            checksum = struct.unpack(">I", data[offset + 8 + size:offset + 12 + size])[0]
            assert zlib.crc32(kind + payload) & 0xffffffff == checksum
            assert kind not in {b"tEXt", b"iTXt", b"zTXt", b"eXIf"}
            kinds.append(kind)
            offset += 12 + size
        assert kinds[0] == b"IHDR" and kinds[-1] == b"IEND" and b"IDAT" in kinds
    except (AssertionError, IndexError, struct.error):
        return [f"{path}: invalid PNG or unexpected embedded metadata"]
    return []


def check_snapshot(files: dict[str, bytes]) -> list[str]:
    manifest = files.get(".public-files", b"").decode("utf-8")
    allowed = {line.strip() for line in manifest.splitlines() if line.strip() and not line.startswith("#")}
    errors = []
    for path, data in files.items():
        if path not in allowed:
            errors.append(f"{path}: absent from reviewed public-file allowlist")
        suffix = PurePosixPath(path).suffix.lower()
        if (path.startswith("data/") and path not in {"data/.gitkeep", "data/README.md"}) or suffix in {
            ".xlsx", ".xls", ".xlsm", ".jsonl", ".db", ".sqlite", ".sqlite3", ".pem", ".key"
        } or path == "static/demo.html" or path.startswith(("private/", "exports/", "secrets/")) or PurePosixPath(path).name.startswith(".env"):
            errors.append(f"{path}: private artifact type or location")
        errors.extend(check_png(path, data) if suffix == ".png" else check_text(path, data))
    for missing in sorted(allowed - files.keys()):
        errors.append(f"{missing}: allowlisted file missing from snapshot")
    try:
        # Evaluate the snapshot's generator, never a different working-tree copy.
        namespace = {"__file__": str(ROOT / "build_public_demo.py"), "__name__": "public_release_check"}
        exec(compile(files["build_public_demo.py"], "build_public_demo.py", "exec"), namespace)
        html = files["static/public_demo.html"].decode("utf-8")
        payload = json.loads(html.split("const DATA = ", 1)[1].split(";\n", 1)[0])
        if payload != namespace["build_public_payload"]():
            errors.append("static/public_demo.html: differs from synthetic payload")
    except Exception:
        errors.append("static/public_demo.html: cannot verify synthetic payload")
    return errors


def snapshot(staged: bool, ref: str) -> tuple[dict[str, bytes], list[str]]:
    entries = git("ls-files", "--stage", "-z") if staged else git("ls-tree", "-r", "-z", ref)
    files, errors = {}, []
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        path = name.decode("utf-8")
        mode, second, third = metadata.decode().split()
        oid = second if staged else third
        if mode not in {"100644", "100755"} or (staged and third != "0"):
            errors.append(f"{path}: unsupported mode or unresolved conflict")
            continue
        files[path] = git("cat-file", "blob", oid)
    return files, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--ref", default="HEAD")
    parser.add_argument("--history", action="store_true", help="Check every reachable commit and both identity emails")
    parser.add_argument("--check-identity", action="store_true", help="Check the identity Git would use for the next commit")
    args = parser.parse_args()
    errors = []
    refs = git("rev-list", args.ref).decode().splitlines() if args.history else [args.ref]
    if args.staged and args.history:
        parser.error("--staged and --history cannot be combined")
    for ref in refs:
        files, inventory_errors = snapshot(args.staged, ref)
        errors.extend(inventory_errors + check_snapshot(files))
        if args.history:
            emails = git("show", "-s", "--format=%ae%n%ce", ref).decode().splitlines()
            if not all(noreply(email) for email in emails):
                errors.append(f"{ref[:12]}: author or committer email is not a GitHub noreply address")
    if args.check_identity:
        for role in ("GIT_AUTHOR_IDENT", "GIT_COMMITTER_IDENT"):
            identity = git("var", role).decode()
            email = re.search(r"<([^>]+)>", identity)
            if not email or not noreply(email.group(1)):
                errors.append(f"{role}: configure a GitHub noreply email before committing")
    if errors:
        for error in sorted(set(errors)):
            print(error, file=sys.stderr)
        return 1
    print(f"Public release check passed ({len(refs)} snapshot(s)).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
