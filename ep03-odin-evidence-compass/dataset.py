"""Deterministic insurance operations graph for observing Odin as released."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Relationship:
    source: str
    relation: str
    target: str
    source_document: str
    confidence: float


def _entities(prefix: str, entity_type: str, names: list[str]) -> list[dict[str, str]]:
    return [
        {"_key": f"{prefix}_{index:02d}", "name": name, "type": entity_type}
        for index, name in enumerate(names)
    ]


def _numbered_entities(
    prefix: str,
    entity_type: str,
    start: int,
    stop: int,
    label: str,
) -> list[dict[str, str]]:
    return [
        {"_key": f"{prefix}_{index:02d}", "name": f"{label}{index:03d}", "type": entity_type}
        for index in range(start, stop)
    ]


ENTITIES = [
    *_entities(
        "claim",
        "claim",
        [
            "Claim 1042",
            "Claim 1088",
            "Claim 1116",
            "Claim 1173",
            "Claim 1210",
            "Claim 1264",
            "Claim 1301",
            "Claim 1349",
            "Claim 1407",
            "Claim 1452",
            "Claim 1518",
            "Claim 1580",
        ],
    ),
    *_entities(
        "person",
        "person",
        [
            "Ana Torres",
            "Ben Okafor",
            "Chen Wei",
            "Dina Shah",
            "Elias Mensah",
            "Farah Noor",
            "Grace Kim",
            "Hugo Martin",
            "Imani Cole",
            "Jon Bell",
        ],
    ),
    *_entities(
        "vehicle",
        "vehicle",
        [
            "Vehicle V-204",
            "Vehicle V-317",
            "Vehicle V-422",
            "Vehicle V-518",
            "Vehicle V-603",
            "Vehicle V-711",
            "Vehicle V-846",
            "Vehicle V-932",
        ],
    ),
    *_entities(
        "policy",
        "policy",
        [
            "Policy P-2201",
            "Policy P-2248",
            "Policy P-2304",
            "Policy P-2377",
            "Policy P-2419",
            "Policy P-2482",
            "Policy P-2536",
            "Policy P-2590",
        ],
    ),
    *_entities(
        "garage",
        "garage",
        [
            "Northside Auto",
            "Central Repairs",
            "Riverside Bodyworks",
            "Eastgate Motors",
            "Harbor Collision",
            "Summit Auto Care",
        ],
    ),
    *_entities(
        "assessor",
        "assessor",
        [
            "Sam Malik",
            "Jordan Lee",
            "Priya Raman",
            "Theo Grant",
            "Maya Silva",
            "Noah Wright",
        ],
    ),
    *_entities(
        "address",
        "address",
        [
            "14 Cedar Road",
            "88 Market Street",
            "6 Harbor Lane",
            "42 Ridge Avenue",
            "19 Willow Close",
            "73 Station Way",
        ],
    ),
    *_entities(
        "device",
        "device",
        [
            "Device D-18A",
            "Device D-27F",
            "Device D-33C",
            "Device D-41B",
            "Device D-59E",
        ],
    ),
    *_entities(
        "account",
        "payment_account",
        [
            "Account A-109",
            "Account A-224",
            "Account A-371",
            "Account A-448",
            "Account A-592",
        ],
    ),
    *_numbered_entities("claim", "claim", 12, 120, "Historical Claim "),
    *_numbered_entities("person", "person", 10, 140, "Claimant "),
    *_numbered_entities("vehicle", "vehicle", 8, 120, "Vehicle V-"),
    *_numbered_entities("policy", "policy", 8, 120, "Policy P-"),
    *_numbered_entities("garage", "garage", 6, 30, "Repair Network "),
    *_numbered_entities("assessor", "assessor", 6, 25, "Assessor "),
    *_numbered_entities("address", "address", 6, 100, "Address "),
    *_numbered_entities("device", "device", 5, 60, "Device D-"),
    *_numbered_entities("account", "payment_account", 5, 60, "Account A-"),
]


def _relationship(
    source: str,
    relation: str,
    target: str,
    sequence: int,
    confidence: float,
) -> Relationship:
    return Relationship(
        source=source,
        relation=relation,
        target=target,
        source_document=f"record_{sequence:03d}",
        confidence=confidence,
    )


def build_relationships() -> list[Relationship]:
    relationships: list[Relationship] = []

    def add(source: str, relation: str, target: str, confidence: float) -> None:
        relationships.append(
            _relationship(
                source,
                relation,
                target,
                len(relationships) + 1,
                confidence,
            )
        )

    # Hand-designed topology. Docket: claims 00-04 (pending, payable_to).
    # Ring: claims 00 and 03 (docket) plus 05 and 08 (historical) connect
    # through accounts controlled by person_09 (Jon Bell), device_02, and
    # garage_02. Nothing on any single claim record is anomalous.
    # Clean claims stay inside their claimant's own cluster.
    #
    # Per claim: (person, vehicle, policy, garage, assessor, device, account)
    # device/account of None means the record has no such entry.
    claims = {
        "claim_00": ("person_00", "vehicle_00", "policy_00", "garage_02", "assessor_00", "device_02", ("payable_to", "account_00")),  # ring A
        "claim_01": ("person_01", "vehicle_01", "policy_01", "garage_00", "assessor_01", "device_00", ("payable_to", "account_02")),
        "claim_02": ("person_02", "vehicle_02", "policy_02", "garage_01", "assessor_02", "device_01", ("payable_to", "account_03")),
        "claim_03": ("person_03", "vehicle_03", "policy_03", "garage_04", "assessor_03", "device_02", ("payable_to", "account_01")),  # ring B
        "claim_04": ("person_04", "vehicle_04", "policy_04", "garage_03", "assessor_04", "device_03", ("payable_to", "account_04")),
        "claim_05": ("person_07", "vehicle_05", "policy_05", "garage_02", "assessor_05", "device_02", ("settled_to", "account_00")),  # ring history
        "claim_06": ("person_05", "vehicle_06", "policy_06", "garage_05", "assessor_00", None, None),
        "claim_07": ("person_06", "vehicle_07", "policy_07", "garage_05", "assessor_01", None, None),
        "claim_08": ("person_09", "vehicle_05", "policy_05", "garage_02", "assessor_05", "device_02", ("settled_to", "account_01")),  # ring history
        "claim_09": ("person_06", "vehicle_07", "policy_07", "garage_05", "assessor_02", None, None),
        "claim_10": ("person_01", "vehicle_01", "policy_01", "garage_00", "assessor_03", "device_00", ("settled_to", "account_02")),
        "claim_11": ("person_02", "vehicle_02", "policy_02", "garage_01", "assessor_04", "device_01", ("settled_to", "account_03")),
    }
    for claim, (person, vehicle, policy, garage, assessor, device, payment) in claims.items():
        add(claim, "submitted_by", person, 0.99)
        add(claim, "covers_vehicle", vehicle, 0.98)
        add(claim, "under_policy", policy, 1.0)
        add(claim, "repaired_at", garage, 0.97)
        add(claim, "assessed_by", assessor, 0.98)
        if device is not None:
            add(claim, "filed_from", device, 0.96)
        if payment is not None:
            relation, account = payment
            add(claim, relation, account, 0.99)

    for person, address in {
        "person_00": "address_00",
        "person_01": "address_01",
        "person_02": "address_02",
        "person_03": "address_03",
        "person_04": "address_04",
        "person_09": "address_05",  # ring: Jon Bell lives at the garage_02 address
    }.items():
        add(person, "lives_at", address, 0.99)

    for person, (policy, vehicle) in {
        "person_00": ("policy_00", "vehicle_00"),
        "person_01": ("policy_01", "vehicle_01"),
        "person_02": ("policy_02", "vehicle_02"),
        "person_03": ("policy_03", "vehicle_03"),
        "person_04": ("policy_04", "vehicle_04"),
        "person_05": ("policy_06", "vehicle_06"),
        "person_06": ("policy_07", "vehicle_07"),
        "person_07": ("policy_05", "vehicle_05"),
    }.items():
        add(person, "holds_policy", policy, 1.0)
        add(person, "owns_vehicle", vehicle, 0.98)

    for person, device in {
        "person_01": "device_00",
        "person_02": "device_01",
        "person_09": "device_02",  # ring: the shared filing device is Jon Bell's
        "person_04": "device_03",
        "person_08": "device_04",
    }.items():
        add(person, "uses_device", device, 0.95)

    for vehicle, garage in {
        "vehicle_00": "garage_02",
        "vehicle_01": "garage_00",
        "vehicle_02": "garage_01",
        "vehicle_03": "garage_04",
        "vehicle_04": "garage_03",
        "vehicle_05": "garage_02",
        "vehicle_06": "garage_05",
        "vehicle_07": "garage_05",
    }.items():
        add(vehicle, "serviced_at", garage, 0.97)

    for index in range(5):
        add(f"vehicle_{index:02d}", "registered_at", f"address_{index:02d}", 0.99)

    for index in range(8):
        add(f"policy_{index:02d}", "insures_vehicle", f"vehicle_{index:02d}", 1.0)

    for policy, account in {
        "policy_00": "account_00",  # ring: Ana's premiums flow through Jon Bell's account
        "policy_01": "account_02",
        "policy_02": "account_03",
        "policy_03": "account_01",  # ring: Dina's premiums flow through Jon Bell's account
        "policy_04": "account_04",
    }.items():
        add(policy, "billed_to", account, 0.99)

    add("garage_02", "located_at", "address_05", 1.0)
    add("garage_02", "paid_to", "account_00", 0.98)

    for device, person in {
        "device_00": "person_01",
        "device_01": "person_02",
        "device_02": "person_09",
        "device_03": "person_04",
        "device_04": "person_08",
    }.items():
        add(device, "registered_to", person, 0.96)

    for account, person in {
        "account_00": "person_09",
        "account_01": "person_09",
        "account_02": "person_01",
        "account_03": "person_02",
        "account_04": "person_04",
    }.items():
        add(account, "controlled_by", person, 0.98)

    # Historical background. The modular assignments produce overlapping but
    # explainable operational neighborhoods instead of isolated claim stars.
    # Devices/accounts 05-09 are shared facilities operated by repair networks;
    # their reuse is intentionally benign and must not imply escalation alone.
    docket_garages = ("garage_02", "garage_00", "garage_01", "garage_04", "garage_03")
    docket_assessors = ("assessor_00", "assessor_01", "assessor_02", "assessor_03", "assessor_04")
    for claim_index in range(12, 120):
        claim = f"claim_{claim_index:02d}"
        history_offset = claim_index - 12
        docket_cluster = history_offset % 5
        cluster_position = history_offset // 5
        person = f"person_{10 + history_offset % 108:02d}"
        vehicle = f"vehicle_{8 + (claim_index - 12) % 112:02d}"
        policy = f"policy_{8 + (claim_index - 12) % 112:02d}"
        garage = (
            docket_garages[docket_cluster]
            if cluster_position % 3 != 2
            else f"garage_{6 + history_offset % 24:02d}"
        )
        assessor = (
            docket_assessors[docket_cluster]
            if cluster_position % 4 != 3
            else f"assessor_{6 + history_offset % 19:02d}"
        )
        device = (
            f"device_{5 + docket_cluster:02d}"
            if cluster_position % 5 == 0
            else f"device_{10 + history_offset % 50:02d}"
        )
        account = (
            f"account_{5 + docket_cluster:02d}"
            if cluster_position % 6 == 0
            else f"account_{10 + history_offset % 50:02d}"
        )
        add(claim, "submitted_by", person, 0.99)
        add(claim, "covers_vehicle", vehicle, 0.98)
        add(claim, "under_policy", policy, 1.0)
        add(claim, "repaired_at", garage, 0.97)
        add(claim, "assessed_by", assessor, 0.98)
        add(claim, "filed_from", device, 0.96)
        add(claim, "settled_to", account, 0.99)

    for person_index in range(10, 140):
        person = f"person_{person_index:02d}"
        address = f"address_{(person_index - 10) % 100:02d}"
        device = f"device_{10 + (person_index - 10) % 50:02d}"
        add(person, "lives_at", address, 0.99)
        add(person, "uses_device", device, 0.95)

    for vehicle_index in range(8, 120):
        vehicle = f"vehicle_{vehicle_index:02d}"
        garage = f"garage_{(vehicle_index - 8) % 30:02d}"
        address = f"address_{(vehicle_index - 8) % 100:02d}"
        add(vehicle, "serviced_at", garage, 0.97)
        add(vehicle, "registered_at", address, 0.99)

    for policy_index in range(8, 120):
        policy = f"policy_{policy_index:02d}"
        vehicle = f"vehicle_{policy_index:02d}"
        account = f"account_{5 + (policy_index - 8) % 55:02d}"
        add(policy, "insures_vehicle", vehicle, 1.0)
        add(policy, "billed_to", account, 0.99)

    for garage_index in range(6, 30):
        garage = f"garage_{garage_index:02d}"
        address = f"address_{6 + (garage_index - 6) % 94:02d}"
        account = f"account_{5 + (garage_index - 6) % 55:02d}"
        add(garage, "located_at", address, 1.0)
        add(garage, "paid_to", account, 0.98)

    for assessor_index in range(6, 25):
        garage = f"garage_{6 + (assessor_index - 6) % 24:02d}"
        add(f"assessor_{assessor_index:02d}", "accredited_at", garage, 0.97)

    for device_index in range(5, 60):
        device = f"device_{device_index:02d}"
        if device_index < 10:
            add(device, "operated_by", f"garage_{device_index + 1:02d}", 0.99)
        else:
            person_index = 10 + (device_index - 10) % 130
            add(device, "registered_to", f"person_{person_index:02d}", 0.96)

    for account_index in range(5, 60):
        account = f"account_{account_index:02d}"
        if account_index < 10:
            add(account, "managed_by", f"garage_{account_index + 1:02d}", 0.99)
        else:
            person_index = 10 + (account_index - 10) % 130
            add(account, "controlled_by", f"person_{person_index:02d}", 0.98)

    # Connect the unused identity-only device from the compact fixture to a
    # sourced address cluster without making it part of the suspicious ring.
    add("person_08", "lives_at", "address_06", 0.99)

    # Odin traverses directed edges. Materialize explicit inverse claim roles
    # from shared entities so a follow-up seed can navigate into related cases.
    # Each inverse edge retains the forward edge's source record and confidence.
    inverse_claim_relations = {
        "submitted_by": "submitted_claim",
        "covers_vehicle": "involved_in_claim",
        "under_policy": "received_claim",
        "repaired_at": "repaired_claim",
        "assessed_by": "assessed_claim",
        "filed_from": "filed_claim",
        "payable_to": "received_payment_for",
        "settled_to": "received_payment_for",
    }
    for item in tuple(relationships):
        inverse_relation = inverse_claim_relations.get(item.relation)
        if inverse_relation is None:
            continue
        relationships.append(Relationship(
            source=item.target,
            relation=inverse_relation,
            target=item.source,
            source_document=item.source_document,
            confidence=item.confidence,
        ))

    return relationships


RELATIONSHIPS = build_relationships()


def _hops_to(start: str, goal: str, adjacency: dict[str, set[str]]) -> int:
    """Undirected BFS distance; large sentinel when unreachable."""
    frontier, seen, distance = {start}, {start}, 0
    while frontier:
        if goal in frontier:
            return distance
        frontier = {n for node in frontier for n in adjacency[node]} - seen
        seen |= frontier
        distance += 1
    return 10_000


def validate_dataset() -> dict[str, object]:
    entity_keys = [entity["_key"] for entity in ENTITIES]
    relationships = [
        (item.source, item.relation, item.target) for item in RELATIONSHIPS
    ]
    participating_entities = {
        entity_id
        for item in RELATIONSHIPS
        for entity_id in (item.source, item.target)
    }

    assert len(ENTITIES) == 775
    assert len(RELATIONSHIPS) == 2619
    assert len(entity_keys) == len(set(entity_keys))
    assert len(relationships) == len(set(relationships))
    assert all(item.source in entity_keys for item in RELATIONSHIPS)
    assert all(item.target in entity_keys for item in RELATIONSHIPS)
    assert all(item.source != item.target for item in RELATIONSHIPS)
    assert all(item.source_document for item in RELATIONSHIPS)
    assert participating_entities == set(entity_keys)

    # Docket contract: claims 00-04 pending (payable_to); all others historical.
    docket = {f"claim_{index:02d}" for index in range(5)}
    payable = {item.source for item in RELATIONSHIPS if item.relation == "payable_to"}
    assert payable == docket

    # Ring topology: both Jon Bell accounts, the shared device, and the garage.
    ring_accounts = {
        item.source
        for item in RELATIONSHIPS
        if item.relation == "controlled_by" and item.target == "person_09"
    }
    assert ring_accounts == {"account_00", "account_01"}
    filed_from_ring_device = {
        item.source
        for item in RELATIONSHIPS
        if item.relation == "filed_from" and item.target == "device_02"
    }
    assert filed_from_ring_device == {"claim_00", "claim_03", "claim_05", "claim_08"}
    repaired_at_ring_garage = {
        item.source
        for item in RELATIONSHIPS
        if item.relation == "repaired_at" and item.target == "garage_02"
    }
    assert {"claim_00", "claim_05", "claim_08"}.issubset(repaired_at_ring_garage)
    assert len(repaired_at_ring_garage) > 3

    # Benign reuse contract: shared intake devices are institutionally operated.
    # This gives the agent plausible shared infrastructure it must distinguish
    # from the independently corroborated ring around person_09.
    for device_index in range(5, 10):
        device = f"device_{device_index:02d}"
        filing_claims = {
            item.source
            for item in RELATIONSHIPS
            if item.relation == "filed_from" and item.target == device
        }
        operators = {
            item.target
            for item in RELATIONSHIPS
            if item.source == device and item.relation == "operated_by"
        }
        assert len(filing_claims) >= 2
        assert operators == {f"garage_{device_index + 1:02d}"}

    # Distance contract: ring docket claims reach Jon Bell in <=2 hops;
    # clean docket claims stay far away, so navigation cannot false-flag them.
    adjacency: dict[str, set[str]] = {key: set() for key in entity_keys}
    for item in RELATIONSHIPS:
        adjacency[item.source].add(item.target)
        adjacency[item.target].add(item.source)
    reachable = {"claim_00"}
    frontier = {"claim_00"}
    while frontier:
        frontier = {neighbor for node in frontier for neighbor in adjacency[node]} - reachable
        reachable |= frontier
    assert reachable == set(entity_keys)
    for ring_claim in ("claim_00", "claim_03"):
        assert _hops_to(ring_claim, "person_09", adjacency) <= 2
    for clean_claim in ("claim_01", "claim_02", "claim_04"):
        assert _hops_to(clean_claim, "person_09", adjacency) > 4

    # Every docket claim sits inside a mixed historical neighborhood rather
    # than hanging from the generated graph through a single articulation.
    for docket_claim in sorted(docket):
        distances = {docket_claim: 0}
        frontier = {docket_claim}
        for distance in range(1, 4):
            frontier = {
                neighbor
                for node in frontier
                for neighbor in adjacency[node]
                if neighbor not in distances
            }
            distances.update({node: distance for node in frontier})
        historical_claims = {
            node for node in distances
            if node.startswith("claim_") and node not in docket
        }
        assert len(distances) >= 140
        assert len(historical_claims) >= 15

    return {
        "entities": len(ENTITIES),
        "relationships": len(RELATIONSHIPS),
        "entity_types": dict(Counter(entity["type"] for entity in ENTITIES)),
        "relation_types": dict(Counter(item.relation for item in RELATIONSHIPS)),
        "seed_out_degree": sum(
            item.source == "claim_00" for item in RELATIONSHIPS
        ),
    }


if __name__ == "__main__":
    print(validate_dataset())