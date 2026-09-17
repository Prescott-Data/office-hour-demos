"""Load the frozen verification dataset into a dedicated ArangoDB database."""

from __future__ import annotations

import os

from arango import ArangoClient

from dataset import ENTITIES, RELATIONSHIPS, validate_dataset


DATABASE_NAME = os.getenv("ODIN_DEMO_DATABASE", "odin_demo_validation")


def get_database(*, reset: bool = False):
    client = ArangoClient(hosts=os.getenv("ARANGO_URL", "http://localhost:8529"))
    username = os.getenv("ARANGO_USERNAME", "root")
    password = os.getenv("ARANGO_PASSWORD", "odin-demo")
    system_database = client.db("_system", username=username, password=password)

    if reset and system_database.has_database(DATABASE_NAME):
        system_database.delete_database(DATABASE_NAME)
    if not system_database.has_database(DATABASE_NAME):
        system_database.create_database(DATABASE_NAME)

    return client.db(DATABASE_NAME, username=username, password=password)


def load_graph(*, reset: bool = True):
    manifest = validate_dataset()
    document_relationships: dict[str, set[str]] = {}
    for relationship in RELATIONSHIPS:
        document_relationships.setdefault(relationship.source_document, set()).add(relationship.relation)
    database = get_database(reset=reset)
    database.create_collection("ExtractedEntities")
    database.create_collection("ExtractedRelationships", edge=True)
    database.create_collection("Documents")
    database.create_collection("EXTRACTED_FROM", edge=True)

    database.collection("ExtractedEntities").import_bulk(
        ENTITIES,
        on_duplicate="error",
    )
    database.collection("Documents").import_bulk(
        [
            {
                "_key": document_id,
                "title": f"Operational record {document_id}",
                "relationship_types": sorted(relationship_types),
            }
            for document_id, relationship_types in document_relationships.items()
        ],
        on_duplicate="error",
    )
    database.collection("ExtractedRelationships").import_bulk(
        [
            {
                "_key": f"relationship_{index:03d}",
                "_from": f"ExtractedEntities/{relationship.source}",
                "_to": f"ExtractedEntities/{relationship.target}",
                "relationship": relationship.relation,
                "weight": 1.0,
                "raw_confidence": relationship.confidence,
                "created_at": "2026-08-01T12:00:00Z",
                "source_document_id": f"Documents/{relationship.source_document}",
            }
            for index, relationship in enumerate(RELATIONSHIPS, start=1)
        ],
        on_duplicate="error",
    )

    return database, manifest


if __name__ == "__main__":
    loaded_database, loaded_manifest = load_graph()
    print(
        f"Loaded {loaded_manifest['entities']} entities and "
        f"{loaded_manifest['relationships']} relationships into "
        f"{loaded_database.name}."
    )