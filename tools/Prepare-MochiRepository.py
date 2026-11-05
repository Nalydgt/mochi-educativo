"""Plan or export an allowlisted, private MOCHI monorepo without changing sources.

Default is read-only planning. --write creates a fresh directory exclusively;
it never deletes, moves, overwrites, stages, commits, publishes, or pushes files.
Secret reports contain paths/rules/counts only, never matched values or lines.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
CODE = {".c", ".cc", ".cpp", ".h", ".hh", ".hpp", ".s", ".ld", ".inc", ".cmake", ".py", ".ps1", ".sh", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".css", ".scss", ".html", ".sql", ".toml", ".yaml", ".yml", ".json", ".lock", ".md"}
IMAGES = {".png", ".svg", ".webp", ".jpg", ".jpeg", ".ico", ".rgb565a8"}
NAMES = {"CMakeLists.txt", "Kconfig", "Kconfig.projbuild", "Dockerfile", "Makefile", "README", "LICENSE", "NOTICE", "requirements.txt", ".gitignore", ".dockerignore", ".prettierrc", ".prettierignore", ".vercelignore", ".env.example"}
BLOCKED_DIRS = {".runtime", ".references", ".git", ".vercel", "backups", "backup", "build", "build-ota", "managed_components", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache", ".tanstack", ".output", ".nitro", ".vinxi", ".wrangler", ".lovable", "dist", "dist-ssr", "output", "data", "models", "weights", "model-weights", "recordings", "voice-bank", "logs", "fixtures", "references", "referencias", "auditoria", "vistas"}
BLOCKED_SUFFIXES = {".wav", ".pcm", ".mp3", ".mp4", ".mov", ".m4a", ".ogg", ".flac", ".aac", ".sqlite", ".sqlite3", ".db", ".pem", ".key", ".p12", ".pfx", ".jks", ".crt", ".cer", ".log", ".bin", ".gguf", ".onnx", ".pt", ".pth", ".safetensors", ".tflite", ".npz", ".npy", ".zip", ".tar", ".gz", ".7z", ".blend", ".blend1", ".3mf", ".pyc"}
PRIVATE_NAMES = {"sdkconfig", "sdkconfig.old", "export-manifest.json", "nas.json", "credentials.json", "secrets.json", "known_hosts", "id_rsa", "id_ed25519", "authorized_keys"}
TOP_FILES = {"firmware": {"CMakeLists.txt", "dependencies.lock", "sdkconfig.defaults", "sdkconfig.ota.defaults", "partitions.csv", "partitions.ota.csv"}}
WEB_TOP = {"package.json", "package-lock.json", "bun.lock", "bunfig.toml", "components.json", "vite.config.ts", "vitest.config.ts", "tsconfig.json", "eslint.config.js", "drizzle.config.ts", ".prettierrc", ".prettierignore", ".vercelignore"}
TEMPLATES = {
    "README.md": "README.md", "GUIDE.md": "docs/GUIA_MONOREPO.md",
    "SETUP.md": "docs/SETUP.md", "MIGRATIONS.md": "docs/MIGRATIONS.md",
    "EVIDENCE.md": "docs/EVIDENCIA.md", "THIRD_PARTY.md": "licenses/README.md",
    "PERSONAL_USE.md": "USO_PERSONAL.md", "WEB_README.md": "web/README.md",
    "gitignore.template": ".gitignore", "web.env.example": "web/.env.example",
    "EXPORTER.md": "docs/EXPORTADOR.md",
    "COUCOU.md": "COUCOU.md", "nas.example.json": "config/nas.example.json",
    "STATUS.md": "docs/ESTADO_PRODUCTO.md",
}
ROOT_SOURCES = {".gitattributes", "config/asr-small.json", "profiles/mochi/README.md", "profiles/mochi/SOUL.md", "profiles/mochi/SOUL-VOICE.md"}
WEB_SOURCES = {"src/data/peluqo.ts", "fixtures/reviewed-mission.ts"}
MAX_FILE_BYTES = 25 * 1024 * 1024
TEXT_SUFFIXES = CODE | {".txt", ".csv", ".svg", ".ini", ".cfg", ".conf"}
TEXT_NAMES = NAMES | {".gitattributes", "gitignore.template", "web.env.example"}
REVIEW_REASONS = {"synthetic_in_process_test", "synthetic_rejection_only_test", "public_upstream_usage_example", "generated_code_fragment"}


class ExportError(RuntimeError):
    pass


@dataclass(frozen=True)
class Entry:
    source: Path
    source_root: str
    source_relative: str
    destination: str
    data: bytes
    transforms: tuple[str, ...] = ()


def linked(path: Path) -> bool:
    """Reject symlinks and Windows junctions/reparse points, even within roots."""
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def safe_relative(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"..", "."} or ":" in part or "\\" in part for part in path.parts):
        raise ExportError("Unsafe relative destination in export plan")
    return path


def excluded(path: Path, relative: PurePosixPath) -> str | None:
    lower = path.name.lower()
    if linked(path):
        return "link_or_reparse_point"
    if any(part.lower() in BLOCKED_DIRS for part in relative.parts):
        return "runtime_build_private_or_fixture_directory"
    if lower.startswith(".env") and lower != ".env.example":
        return "private_environment"
    if lower in PRIVATE_NAMES or lower.endswith((".sqlite3-wal", ".sqlite3-shm", ".db-wal", ".db-shm")):
        return "private_state"
    if path.suffix.lower() in BLOCKED_SUFFIXES:
        return "recording_model_database_key_or_archive"
    if "secret" in lower and lower.endswith(".json"):
        return "private_secret_state"
    return None


def notice_filename(name: str) -> bool:
    return name.upper().startswith(("LICENSE", "COPYING", "NOTICE", "AUTHORS", "COPYRIGHT")) or name.upper().endswith(("-LICENSE", "-LICENSE.TXT", "-COPYING", "-COPYING.TXT"))


def allowed(relative: PurePosixPath, tree: str) -> bool:
    name, suffix = relative.name, relative.suffix.lower()
    if notice_filename(name):
        return True
    if tree == "firmware":
        if len(relative.parts) == 1:
            return name in TOP_FILES[tree]
        if relative.parts[0] == "assets":
            return suffix in IMAGES | {".json", ".md", ".txt"}
        return relative.parts[0] in {"main", "components", "cmake"} and (suffix in CODE or name in NAMES)
    if tree == "hardware":
        return suffix in {".py", ".scad", ".md"} or name in {"parametros.json", "requirements.txt"} or (suffix == ".stl" and relative.parts[:2] == ("tamapoke-v6", "stl"))
    if tree == "licenses":
        return suffix in {".txt", ".md"} or name in {"LICENSE", "NOTICE"}
    if tree == "tools":
        if relative.parts[0] == "repository-template":
            return relative.as_posix().removeprefix("repository-template/") in TEMPLATES
        if relative.parts[0] == "fonts":
            return suffix in {".ttf", ".md", ".txt"} or name in {"package.json", "package-lock.json"}
        return suffix in CODE or name in NAMES
    if tree in {"services", "gateway"}:
        return suffix in CODE or name in NAMES
    if tree == "web":
        if len(relative.parts) == 1:
            return name in WEB_TOP
        head = relative.parts[0]
        if head == "public":
            return suffix in IMAGES | {".txt"}
        if head == "src":
            return suffix in CODE | IMAGES
        if head in {"tools", "drizzle", "supabase", "deploy"}:
            if head == "deploy" and "private" in relative.parts:
                return False
            return suffix in CODE or name in NAMES
    return False


def transform(destination: str, data: bytes) -> tuple[bytes, tuple[str, ...]]:
    """Only the four explicitly authorized export-layout adjustments."""
    if destination not in {"tools/Check-MochiLessonVoice.py", "web/tools/pilot.py", "web/tools/configure-peluqo-board.py", "web/tools/build-pilot.py"}:
        return data, ()
    source = data.decode("utf-8-sig")
    changed = []
    if destination == "tools/Check-MochiLessonVoice.py":
        source, count = re.subn(r"ROOT\.parent\s*/\s*(['\"])peluqo-mundos([^'\"]*)\1", lambda match: "ROOT / " + match[1] + "web" + match[2] + match[1], source)
        if count:
            changed.append("lesson_voice_uses_root_web")
    elif destination in {"web/tools/pilot.py", "web/tools/configure-peluqo-board.py"}:
        source, count = re.subn(r"(?m)^(\s*(?:MOCHI|mochi)\s*=\s*(?:ROOT|root)\.parent)\s*/\s*(['\"])tamagochi 2\2", r"\1", source)
        if count:
            changed.append("web_tool_uses_monorepo_parent")
    elif destination == "web/tools/build-pilot.py":
        marker = "root=Path(__file__).resolve().parents[1]"
        addition = "(root / '.runtime').mkdir(parents=True, exist_ok=True)"
        if addition not in source:
            if source.count(marker) != 1:
                raise ExportError("build-pilot layout changed; review the explicit export transform")
            source = source.replace(marker, marker + "\n" + addition, 1)
            changed.append("build_pilot_creates_runtime")
    return (source.encode("utf-8"), tuple(changed)) if changed else (data, ())


def normalize_lf(destination: str, data: bytes) -> tuple[bytes, tuple[str, ...]]:
    """Hash and write the same deterministic text bytes that Git preserves."""
    relative = PurePosixPath(destination)
    if (relative.suffix.lower() in TEXT_SUFFIXES or relative.name in TEXT_NAMES or notice_filename(relative.name)) and b"\r\n" in data:
        return data.replace(b"\r\n", b"\n"), ("normalize_lf",)
    return data, ()


def collect(source_root: Path, web_root: Path) -> tuple[list[Entry], Counter]:
    entries: dict[str, Entry] = {}
    omitted = Counter()
    trees = [(source_root / name, name, name) for name in ("firmware", "services", "gateway", "tools", "licenses", "hardware")]
    trees.append((web_root, "web", "web"))
    for base, tree, prefix in trees:
        if not base.is_dir() or linked(base):
            raise ExportError("A required source tree is absent or linked: " + tree)
        resolved_base = base.resolve()
        for directory, directories, files in os.walk(base, followlinks=False):
            current = Path(directory)
            kept = []
            for name in sorted(directories):
                child = current / name
                rel = PurePosixPath(child.relative_to(base).as_posix())
                reason = excluded(child, rel)
                if reason:
                    omitted[reason] += 1
                elif tree == "web" and (rel.parts[:2] == ("deploy", "supabase") or (len(rel.parts) == 1 and name not in {"src", "tools", "drizzle", "supabase", "deploy", "public"})):
                    omitted["directory_not_allowlisted"] += 1
                else:
                    kept.append(name)
            directories[:] = kept
            for name in sorted(files):
                path = current / name
                rel = PurePosixPath(path.relative_to(base).as_posix())
                reason = excluded(path, rel)
                if reason:
                    omitted[reason] += 1
                    continue
                if not allowed(rel, tree):
                    omitted["file_not_allowlisted"] += 1
                    continue
                if not path.resolve().is_relative_to(resolved_base):
                    raise ExportError("A source escapes its allowlisted root")
                if path.stat().st_size > MAX_FILE_BYTES:
                    omitted["oversize_source"] += 1
                    continue
                destination = str(safe_relative(prefix + "/" + rel.as_posix()))
                data, changes = transform(destination, path.read_bytes())
                entries[destination] = Entry(path, tree, rel.as_posix(), destination, data, changes)
    for base, sources, prefix, label in ((source_root, ROOT_SOURCES, "", "root-source"), (web_root, WEB_SOURCES, "web/", "web-reviewed-source")):
        for relative in sorted(sources):
            path = base.joinpath(*safe_relative(relative).parts)
            if not path.is_file() or any(linked(ancestor) for ancestor in (path, *path.parents) if ancestor != base and ancestor.is_relative_to(base)):
                raise ExportError("A required explicit source is absent or linked: " + prefix + relative)
            destination = prefix + relative
            entries[destination] = Entry(path, label, relative, destination, path.read_bytes())
    template_root = source_root / "tools/repository-template"
    cmake = (source_root / "firmware/CMakeLists.txt").read_text(encoding="utf-8")
    version_match = re.search(r'set\(PROJECT_VER\s+"([^"\r\n]+)"\)', cmake)
    version = version_match[1] if version_match else "consulta firmware/CMakeLists.txt"
    for source, destination in TEMPLATES.items():
        path = template_root / source
        if not path.is_file() or linked(path):
            raise ExportError("Missing or linked repository template: " + source)
        data = path.read_text(encoding="utf-8").replace("{{FIRMWARE_VERSION}}", version).encode("utf-8")
        entries[destination] = Entry(path, "template", source, destination, data)
    # Only public, synthetic geometry previews; no captures from real accounts,
    # microphone recordings, QA credentials, lesson answers or SQL result dumps.
    previews = source_root / "docs/mediciones/20261105-lesson-scene-host"
    for name in ("apples-3x3.png", "fish-3x2.png", "cars-3x4.png", "dense-12x4.png", "hub-compact.png", "help.png"):
        path = previews / name
        if path.is_file() and not linked(path):
            destination = "docs/illustrations/" + name
            entries[destination] = Entry(path, "synthetic-preview", name, destination, path.read_bytes())
    # Manually inspected interface-only captures: no child, account, PIN or
    # conversation is visible. Keep this exact allowlist, not all measurements.
    for source_name, name in (("20261106-mochi-menu-real.png", "device-settings.png"),
                              ("20261106-mochi-pin-real.png", "device-adult-pin.png")):
        path = source_root / "docs/mediciones" / source_name
        if path.is_file() and not linked(path):
            destination = "docs/illustrations/" + name
            entries[destination] = Entry(path, "reviewed-interface-capture", source_name, destination, path.read_bytes())
    prepared = []
    for entry in entries.values():
        data, adjustments = normalize_lf(entry.destination, entry.data)
        prepared.append(replace(entry, data=data, transforms=entry.transforms + adjustments))
    return sorted(prepared, key=lambda entry: entry.destination), omitted


PROVIDER_PATTERNS = {
    "private_key_block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"),
    "github_token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{40,})\b"),
    "provider_secret": re.compile(r"\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{24,}|[sr]k_(?:live|test)_[A-Za-z0-9]{16,}|sk_[0-9a-fA-F]{40,}|xox[baprs]-[A-Za-z0-9-]{12,})\b"),
    "cloud_access_key": re.compile(r"\b(?:AKIA[0-9A-Z]{16}|AIza[A-Za-z0-9_-]{30,})\b"),
    "embedded_jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\b"),
}
SECRET_ASSIGNMENT = re.compile(r"(?im)(?<![\w-])(?:[A-Z0-9_]*(?:API_KEY|PRIVATE_KEY|SERVICE_ROLE_KEY|PASSWORD|SECRET|TOKEN)|api[_-]?key|private[_-]?key|password|secret|token|integration[_-]?key|pairing[_-]?key|provision[_-]?key|adult[_-]?pin)\b[\"']?\s*[:=]\s*(?P<quote>[\"'])(?P<value>[^\"'\r\n]{8,})(?P=quote)")
ENV_SECRET = re.compile(r"(?m)^[A-Z][A-Z0-9_]*(?:_KEY|_SECRET|_TOKEN|_PASSWORD|_PIN)\s*=\s*([^\r\n#]+)")
PIN_LITERAL = re.compile(r"(?im)\b(?:adult[_-]?pin|PELUQO_ADULT_PIN)[\"']?\s*[:=]\s*[\"']?([0-9]{4,10})(?![0-9])")
DATABASE_URL = re.compile(r"\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqps?)://[^\s\"'<>]+", re.I)
PATH_REFERENCES = re.compile(r"(?:[A-Z]:[\\/](?:Users|esp|Espressif)[\\/]|tamagochi 2|(?:ROOT|root)\.parent\s*/\s*['\"]peluqo-mundos|path\.join\([^\n]*tamagochi 2)", re.I)


def placeholder(value: str) -> bool:
    value = value.strip().strip("\"'")
    lower = value.lower()
    return not value or len(value) < 8 or lower.startswith("your") or bool(re.search(r"(?:replace|\byour[_ -]|example|placeholder|changeme|sample|(?:^|[-_ ])(?:test|testing|fake|fixture|dummy|synthetic)(?:$|[-_ ])|not[-_ ]a[-_ ]|development[-_ ]|<|\$\{|\{\{|\$env:)", lower)) or len(set(value)) <= 3


def known_secrets(source_root: Path, web_root: Path) -> set[bytes]:
    """Compare local configured credentials without exporting or displaying them."""
    values: set[bytes] = set()
    names = ((source_root, ".runtime/nas.json"), (source_root, ".runtime/mochi-education-device.json"), (web_root, ".runtime/pilot-secrets.json"), (web_root, ".runtime/cloud-database.json"), (web_root, ".runtime/inference-worker.json"), (web_root, ".runtime/mochi-education-device.json"), (web_root, ".runtime/teacher-demo.json"), (web_root, ".runtime/qa-integral-family.json"))
    def visit(data: object, key: str = "") -> None:
        if isinstance(data, dict):
            for name, value in data.items():
                visit(value, str(name))
        elif isinstance(data, list):
            for value in data:
                visit(value, key)
        elif isinstance(data, str) and re.search(r"password|secret|token|key|integration|pairing|provision|adult_pin|dsn|url|database|hermes|service", key, re.I) and len(data) >= (4 if "pin" in key.lower() else 8):
            if re.search(r"(?:file|path|directory)$", key, re.I):
                return
            if key.lower() in {"url", "dsn"} and not re.search(r"://[^/@]+:[^/@]+@", data):
                return
            values.add(data.encode("utf-8"))
    for base, relative in names:
        path = base / relative
        if path.is_file() and not linked(path) and path.stat().st_size < 1024 * 1024:
            try:
                visit(json.loads(path.read_text(encoding="utf-8-sig")))
            except (ValueError, OSError):
                raise ExportError("A local credential reference cannot be safely parsed") from None
    return values


def load_literal_allowlist(path: Path | None) -> list[dict]:
    if path is None:
        return []
    if not path.is_file() or linked(path):
        raise ExportError("Literal allowlist must be an existing, unlinked JSON file")
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError):
        raise ExportError("Cannot safely parse the literal review JSON") from None
    rows = data.get("approved", []) if isinstance(data, dict) else []
    if not isinstance(rows, list) or any(not isinstance(row, dict) or not isinstance(row.get("path"), str) or not re.fullmatch(r"[a-f0-9]{64}", str(row.get("sha256", ""))) or row.get("reason") not in REVIEW_REASONS for row in rows):
        raise ExportError("Invalid literal allowlist; require path, exact file sha256 and an approved public-example reason category")
    return rows


def scan(entries: list[Entry], secrets: set[bytes], approved: list[dict] | None = None) -> dict:
    findings, portability, reviewed = [], [], []
    text_files = 0
    for entry in entries:
        counts = Counter()
        digest = hashlib.sha256(entry.data).hexdigest()
        approval = next((row for row in approved or [] if row["path"] == entry.destination and row["sha256"] == digest and row.get("reason") in REVIEW_REASONS), None)
        for value in secrets:
            if value in entry.data:
                counts["configured_credential_value"] += entry.data.count(value)
        try:
            body = entry.data.decode("utf-8")
            if "\x00" in body:
                raise UnicodeError
            text_files += 1
        except UnicodeError:
            body = ""
        for rule, pattern in PROVIDER_PATTERNS.items():
            matches = list(pattern.finditer(body))
            if matches:
                counts[rule] += len(matches)
        for match in SECRET_ASSIGNMENT.finditer(body):
            if not placeholder(match["value"]):
                counts["literal_secret_attribute"] += 1
        if entry.destination.endswith((".env.example", "web.env.example", ".sh")):
            for match in ENV_SECRET.finditer(body):
                if not placeholder(match[1]):
                    counts["literal_secret_attribute"] += 1
        if approval and counts["literal_secret_attribute"]:
            reviewed.append({"path": entry.destination, "sha256": digest, "count": counts.pop("literal_secret_attribute"), "reason": approval["reason"]})
        if list(PIN_LITERAL.finditer(body)):
            counts["literal_adult_pin"] += len(PIN_LITERAL.findall(body))
        for match in DATABASE_URL.finditer(body):
            authority = match[0].split("://", 1)[1].split("/", 1)[0]
            if "@" in authority and ":" in authority.rsplit("@", 1)[0]:
                password = authority.rsplit("@", 1)[0].split(":", 1)[1]
                if not placeholder(password):
                    counts["database_password_url"] += 1
        if counts:
            findings.append({"path": entry.destination, "fileSha256": digest, "rules": dict(sorted(counts.items())), "count": sum(counts.values())})
        lines = []
        for number, line in enumerate(body.splitlines(), 1):
            without_urls = re.sub(r"(?:https?|file)://\S+", "", line)
            if PATH_REFERENCES.search(without_urls):
                lines.append(number)
        if lines:
            portability.append({"path": entry.destination, "lineNumbers": lines, "count": len(lines)})
    return {"blocked": bool(findings), "scannedFiles": len(entries), "textFiles": text_files, "configuredValuesChecked": len(secrets), "findings": findings, "reviewedLiteralFiles": reviewed, "portabilityReferences": portability, "policy": "Paths, file hashes, rule names and counts only. No matched values or snippets. An exact-file reviewed literal allowlist never suppresses configured credentials, provider tokens, JWTs, database passwords, private key blocks or PIN findings."}


def manifest(entries: list[Entry], omitted: Counter, audit: dict) -> dict:
    return {"format": 1, "createdAt": datetime.now(timezone.utc).isoformat(), "scope": "Private personal/demo source export; mixed third-party licenses, not an all-MIT release", "files": [{"path": entry.destination, "bytes": len(entry.data), "sha256": hashlib.sha256(entry.data).hexdigest(), "sourceRoot": entry.source_root, "sourceRelative": entry.source_relative, "transforms": list(entry.transforms)} for entry in entries], "counts": {"files": len(entries), "bytes": sum(len(entry.data) for entry in entries), "bySourceRoot": dict(Counter(entry.source_root for entry in entries)), "omittedByReason": dict(sorted(omitted.items()))}, "secretScan": {"blocked": audit["blocked"], "findingFiles": len(audit["findings"]), "portabilityFiles": len(audit["portabilityReferences"])}}


def destination_for(source_root: Path, requested: Path | None) -> Path:
    parent = source_root / ".runtime/repository-export"
    base = requested if requested is not None else parent / "mochi-educativo"
    base = base.expanduser().absolute()
    expected = parent.resolve()
    if not base.resolve().is_relative_to(expected) or base.resolve() == expected:
        raise ExportError("Destination must be a new child of .runtime/repository-export")
    for ancestor in (source_root / ".runtime", parent):
        if ancestor.exists() and linked(ancestor):
            raise ExportError("Export parent is linked; refusing to write")
    for ancestor in base.parents:
        if ancestor == parent:
            break
        if ancestor.is_relative_to(parent) and ancestor.exists() and linked(ancestor):
            raise ExportError("A destination ancestor is linked; refusing to write")
    if base.exists():
        base = base.with_name(base.name + "-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    return base


def write_export(entries: list[Entry], report: dict, audit: dict, target: Path) -> None:
    if audit["blocked"]:
        raise ExportError("Secret scan blocked export; review the reported paths locally")
    # Every candidate is already read, hashed, scanned and assigned a safe path.
    # Exclusive creation prevents reuse of an old export, even if it is empty.
    target.parent.mkdir(parents=True, exist_ok=True)
    target.mkdir(mode=0o700, exist_ok=False)
    for entry in entries:
        output = target.joinpath(*safe_relative(entry.destination).parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("xb") as handle:
            handle.write(entry.data)
        if hashlib.sha256(output.read_bytes()).hexdigest() != hashlib.sha256(entry.data).hexdigest():
            raise ExportError("Written hash verification failed; incomplete fresh export retained")
    for name, value in (("REPOSITORY_MANIFEST.json", report), ("SECRET_SCAN.json", audit)):
        with (target / name).open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--web-source", type=Path)
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--literal-allowlist", type=Path, help="Optional reviewed public test/example literals, bound to exact exported file SHA-256; never bypasses real token/known-value findings")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan", action="store_true", help="Read-only plan and scan (default)")
    mode.add_argument("--write", action="store_true", help="Create a fresh, scanned export; never runs Git")
    args = parser.parse_args(argv)
    try:
        root = args.source_root.resolve()
        web = args.web_source.resolve() if args.web_source else root / "web" if (root / "web").is_dir() else root.parent / "peluqo-mundos"
        entries, omitted = collect(root, web)
        audit = scan(entries, known_secrets(root, web), load_literal_allowlist(args.literal_allowlist))
        report = manifest(entries, omitted, audit)
        target = destination_for(root, args.destination)
        summary = {"mode": "write" if args.write else "plan", "destination": target.relative_to(root).as_posix(), "counts": report["counts"], "scan": audit, "transformedFiles": [{"path": entry.destination, "changes": list(entry.transforms)} for entry in entries if entry.transforms]}
        if args.write and not audit["blocked"]:
            write_export(entries, report, audit, target)
            summary["written"] = True
        else:
            summary["written"] = False
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 2 if audit["blocked"] else 0
    except ExportError as error:
        print(json.dumps({"written": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except OSError as error:
        print(json.dumps({"written": False, "error": type(error).__name__, "message": "Filesystem operation failed; no cleanup or source mutation attempted."}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
