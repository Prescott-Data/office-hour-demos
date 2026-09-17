"""Observe released Odin behavior against the frozen verification graph."""

from __future__ import annotations

import importlib.metadata
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import odin
from odin import OdinEngine

from load_graph import load_graph


SEED = "ExtractedEntities/claim_00"
RETRIEVAL_PARAMETERS = {
    "max_paths": 12,
    "hop_limit": 10,
    "beam_width": 32,
}


def entity_name(database, entity_id: str) -> str:
    entity = database.document(entity_id)
    return entity.get("name", entity_id) if entity else entity_id


def write_canonical_artifact(payload: dict) -> Path:
    artifact_directory = Path(__file__).parent / "artifacts"
    artifact_directory.mkdir(parents=True, exist_ok=True)
    artifact_path = artifact_directory / f"odin-retrieve-{payload['call_id']}.json"
    artifact_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return artifact_path


def main() -> None:
    database, dataset_manifest = load_graph(reset=True)
    engine = OdinEngine(
        db=database,
        community_id="global",
        community_mode="none",
    )
    result = engine.retrieve(seeds=[SEED], **RETRIEVAL_PARAMETERS)

    call_id = str(uuid4())
    path_depths = [len(path["edges"]) for path in result["paths"]]
    payload = {
        "call_id": call_id,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "runtime": {
            "odin_version": importlib.metadata.version("odin-engine"),
            "odin_module": str(Path(odin.__file__).resolve()),
        },
        "dataset": dataset_manifest,
        "request": {"seeds": [SEED], **RETRIEVAL_PARAMETERS},
        "observations": {
            "returned_paths": len(result["paths"]),
            "path_depths": path_depths,
            "depth_counts": dict(sorted(Counter(path_depths).items())),
            "deepest_path": max(path_depths, default=0),
        },
        "result": result,
    }
    artifact_path = write_canonical_artifact(payload)

    print(f"Odin version: {payload['runtime']['odin_version']}")
    print(f"Odin module: {payload['runtime']['odin_module']}")
    print(f"Seed: {entity_name(database, SEED)} ({SEED})")
    print(f"Request: {payload['request']}")
    print(f"Observations: {payload['observations']}")
    print(f"Canonical artifact: {artifact_path.resolve()}")

    for index, path in enumerate(result["paths"], start=1):
        print(
            f"\nPath {index} | depth={len(path['edges'])} | "
            f"score={path['score']:.6f}"
        )
        for edge in path["edges"]:
            source = entity_name(database, edge["u"])
            target = entity_name(database, edge["v"])
            print(f"  {source} --{edge['relation']}--> {target}")


if __name__ == "__main__":
    main()