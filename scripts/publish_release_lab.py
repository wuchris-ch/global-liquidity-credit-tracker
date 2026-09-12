"""Refresh the public release laboratory using a dedicated, recoverable store.

The scheduled runner supplies FRED_API_KEY. No private workspace is opened.
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.research.operations import backup, restore
from src.research.release_lab import live_bundle, reconcile_releases, write_bundle
from src.research.release_sources import WORKSPACE
from src.research.revision_study import build_study
from src.research.storage import ResearchStore
from src.research.worker import tick


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", default="data/public-release-lab")
    parser.add_argument("--output", default="data/export/latest/research")
    parser.add_argument("--restore")
    parser.add_argument("--backup")
    parser.add_argument("--prior-public")
    parser.add_argument("--study", action="store_true")
    parser.add_argument("--study-only", action="store_true")
    parser.add_argument("--max-jobs", type=int, default=18)
    args = parser.parse_args()
    if not 1 <= args.max_jobs <= 40:
        parser.error("Job budget must be between 1 and 40")
    store = ResearchStore(args.store)
    if args.restore:
        restore(store, args.restore)
        marker = json.loads(Path(args.restore).with_suffix(".required").read_text())
        if (
            len(store.control.list(WORKSPACE, "release_snapshot"))
            < marker["snapshot_count"]
        ):
            raise ValueError("Public release snapshot history regressed")
    # Reject accidental use of another workspace, including private research data.
    from sqlalchemy import select
    from src.research.control import records

    with store.control.engine.connect() as c:
        if any(
            w != WORKSPACE
            for w in c.execute(select(records.c.workspace).distinct()).scalars()
        ):
            raise ValueError("Public publisher requires its dedicated workspace")
    output = Path(args.output)
    if args.prior_public:
        shutil.copytree(args.prior_public, output, dirs_exist_ok=True)
    # Keep each shipped seed addressable after later Vercel deployments.
    from scripts.replay_release_lab import replay

    root = Path(__file__).resolve().parents[1]
    for name in ("study", "feed"):
        seed_path = root / f"frontend/src/lib/release-{name}.json"
        if seed_path.exists():
            seed = json.loads(seed_path.read_text())
            replay(seed)
            write_bundle(seed, output / "releases" / f"{seed['id']}.json")
            if name == "study" and not (args.study or args.study_only):
                write_bundle(seed, output / "study.json")
    output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(root / "scripts/replay_release_lab.py", output / "replay.py")
    if args.study or args.study_only:
        study = build_study(store)
        draft = store.objects.write(json.dumps(study, sort_keys=True).encode())
        if study["study"]["summary"]["excluded"]:
            raise ValueError(
                f"Study publication held for incomplete initial history. Draft evidence object: {draft}"
            )
        replay(study)
        write_bundle(study, output / "study.json")
        print(
            json.dumps({"study": study["id"], "summary": study["study"]["summary"]}),
            flush=True,
        )
    if not args.study_only:
        reconciliation = reconcile_releases(store)
        print(json.dumps({"reconciliation": reconciliation}), flush=True)
        for _ in range(args.max_jobs):
            job = tick(store, WORKSPACE)
            if job is None:
                break
            print(
                json.dumps(
                    {
                        "series": job["payload"].get("series_id"),
                        "vintage": job["payload"].get("information_date"),
                        "status": job["status"],
                    }
                ),
                flush=True,
            )
        bundle = live_bundle(store)
        replay(bundle)  # Independent raw-response replay is a publication gate.
        write_bundle(bundle, output / "releases" / f"{bundle['id']}.json")
        write_bundle(bundle, output / "index.json")
        print(
            json.dumps(
                {
                    "publication": bundle["id"],
                    "snapshots": len(bundle["snapshots"]),
                    "inbox": len(bundle["inbox"]),
                }
            ),
            flush=True,
        )
    if args.backup:
        receipt = backup(store, args.backup)
        Path(args.backup).with_suffix(".required").write_text(
            json.dumps(
                {
                    "format": "release-lab-state/1",
                    "snapshot_count": len(
                        store.control.list(WORKSPACE, "release_snapshot")
                    ),
                    "backup_files": receipt["files"],
                }
            )
        )
        print(json.dumps({"backup": receipt}), flush=True)


if __name__ == "__main__":
    main()
