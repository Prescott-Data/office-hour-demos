import unittest
from collections import defaultdict

from dataset import ENTITIES, RELATIONSHIPS, validate_dataset


DOCKET = {f"claim_{index:02d}" for index in range(5)}


class DatasetTopologyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adjacency = defaultdict(set)
        for edge in RELATIONSHIPS:
            cls.adjacency[edge.source].add(edge.target)
            cls.adjacency[edge.target].add(edge.source)

    def nodes_within(self, seed: str, hops: int) -> set[str]:
        reached = {seed}
        frontier = {seed}
        for _ in range(hops):
            frontier = {
                neighbor
                for node in frontier
                for neighbor in self.adjacency[node]
                if neighbor not in reached
            }
            reached |= frontier
        return reached

    def test_manifest_and_provenance_are_complete(self):
        manifest = validate_dataset()

        self.assertEqual(manifest["entities"], 775)
        self.assertEqual(manifest["relationships"], 2619)
        self.assertTrue(all(edge.source_document for edge in RELATIONSHIPS))

    def test_each_docket_claim_has_a_mixed_historical_neighborhood(self):
        for claim in DOCKET:
            neighborhood = self.nodes_within(claim, 3)
            historical_claims = {
                node
                for node in neighborhood
                if node.startswith("claim_") and node not in DOCKET
            }

            self.assertGreaterEqual(len(neighborhood), 140, claim)
            self.assertGreaterEqual(len(historical_claims), 15, claim)

    def test_shared_intake_devices_have_recorded_institutional_operators(self):
        for device_index in range(5, 10):
            device = f"device_{device_index:02d}"
            filing_claims = {
                edge.source
                for edge in RELATIONSHIPS
                if edge.relation == "filed_from" and edge.target == device
            }
            operators = {
                edge.target
                for edge in RELATIONSHIPS
                if edge.source == device and edge.relation == "operated_by"
            }

            self.assertGreaterEqual(len(filing_claims), 4, device)
            self.assertEqual(operators, {f"garage_{device_index + 1:02d}"})

    def test_bridge_entities_can_navigate_outward_to_related_claims(self):
        routes = {(edge.source, edge.relation, edge.target) for edge in RELATIONSHIPS}

        self.assertIn(("device_02", "filed_claim", "claim_00"), routes)
        self.assertIn(("device_02", "filed_claim", "claim_03"), routes)
        self.assertIn(("garage_02", "repaired_claim", "claim_00"), routes)
        self.assertTrue(any(
            source == "garage_02" and relation == "repaired_claim" and target not in DOCKET
            for source, relation, target in routes
        ))

    def test_suspicious_ring_has_independent_device_and_payment_routes(self):
        routes = {(edge.source, edge.relation, edge.target) for edge in RELATIONSHIPS}

        self.assertIn(("claim_00", "filed_from", "device_02"), routes)
        self.assertIn(("device_02", "registered_to", "person_09"), routes)
        self.assertIn(("claim_03", "filed_from", "device_02"), routes)
        self.assertIn(("claim_00", "payable_to", "account_00"), routes)
        self.assertIn(("account_00", "controlled_by", "person_09"), routes)
        self.assertIn(("claim_03", "payable_to", "account_01"), routes)
        self.assertIn(("account_01", "controlled_by", "person_09"), routes)

    def test_all_entities_are_in_the_docket_component(self):
        self.assertEqual(self.nodes_within("claim_00", len(ENTITIES)), {entity["_key"] for entity in ENTITIES})


if __name__ == "__main__":
    unittest.main()
