"""Portable backups, verification and non-destructive retention planning."""

import json
import shutil
from pathlib import Path

from sqlalchemy import insert, select

from .control import records
from .storage import canonical, digest


def backup(store, destination):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    # Immutable objects written before database records. Snapshot DB first,
    # then copy objects. Concurrent new objects are harmless extras.
    with store.control.engine.connect() as connection:
        rows = [dict(r) for r in connection.execute(select(records)).mappings()]
    shutil.copytree(store.objects.root, destination / "objects")
    (destination / "records.json").write_bytes(canonical(rows))
    hashes = {
        str(p.relative_to(destination)): digest(p.read_bytes())
        for p in destination.rglob("*")
        if p.is_file()
    }
    (destination / "backup.json").write_bytes(
        canonical({"format": "1.0", "files": hashes})
    )
    return verify_backup(destination)


def verify_backup(destination):
    root = Path(destination)
    manifest = json.loads((root / "backup.json").read_bytes())
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if root.resolve() not in path.parents or digest(path.read_bytes()) != expected:
            raise ValueError("Backup integrity failure")
    rows = json.loads((root / "records.json").read_bytes())
    index = {(r["workspace"], r["kind"], r["id"]): json.loads(r["body"]) for r in rows}

    def object_bytes(identifier):
        path = root / "objects" / identifier[:2] / identifier
        if not path.exists() or digest(path.read_bytes()) != identifier:
            raise ValueError("Backup dependency missing or corrupt")
        return path.read_bytes()

    for (workspace, kind, identifier), body in index.items():
        if kind == "capture":
            object_bytes(body["body"])
        if kind in ("run", "model_run"):
            object_bytes(body["artifact"])
        if kind == "head" and (workspace, "manifest", body["manifest"]) not in index:
            raise ValueError("Backup head lacks a committed manifest")
        if kind == "manifest":
            data = json.loads(object_bytes(body["object"]))
            for snapshot in data["snapshots"]:
                object_bytes(snapshot["part"])
                if any(
                    (workspace, "capture", cap) not in index
                    for cap in snapshot["captures"]
                ):
                    raise ValueError("Backup lacks referenced capture")
    return {
        "status": "verified",
        "files": len(manifest["files"]),
        "dependency_closure": True,
    }


def restore(store, source):
    verify_backup(source)
    with store.control.transaction() as tx:
        if tx.execute(select(records).limit(1)).first():
            raise ValueError("Restore requires an empty destination")
        for path in (Path(source) / "objects").rglob("*"):
            if path.is_file():
                if digest(path.read_bytes()) != path.name:
                    raise ValueError("Invalid backed-up object")
                store.objects.write(path.read_bytes())
        rows = json.loads((Path(source) / "records.json").read_bytes())
        if rows:
            tx.execute(insert(records), rows)
    return {"status": "restored", "records": len(rows)}


def retention_plan(store):
    # No automated deletion until dependency closure and rights are reviewed.
    files = [p for p in store.objects.root.rglob("*") if p.is_file()]
    return {
        "dry_run": True,
        "objects": len(files),
        "bytes": sum(p.stat().st_size for p in files),
        "deletions": [],
        "policy": "Retain all evidence. Review explicit references and rights before deleting.",
    }
