import unittest

from scripts.mimic_structured_ehr_ablation import build_arm, target_hits


class MimicStructuredEhrAblationTest(unittest.TestCase):
    def sample_case(self):
        return {
            "case_id": "mimic_iv_example",
            "demographics": {"age_at_diagnosis_years": 42, "sex": "female"},
            "gold_label": {
                "orphanet_id": "ORPHA:1",
                "disease_name": "Target disease",
            },
            "metadata": {
                "primary_relation": "E",
                "all_orpha_hits": [
                    {
                        "orpha_id": "ORPHA:1",
                        "orpha_name": "Target disease",
                        "icd_code": "A001",
                        "icd_title": "Target disease title",
                    },
                    {
                        "orpha_id": "ORPHA:2",
                        "orpha_name": "Other disease",
                        "icd_code": "B002",
                        "icd_title": "Other coded condition",
                    },
                ],
            },
        }

    def test_target_hits_are_linked_by_orpha_id(self):
        self.assertEqual(
            [hit["icd_code"] for hit in target_hits(self.sample_case())],
            ["A001"],
        )

    def test_title_selection_contains_titles(self):
        arm = build_arm(self.sample_case(), "title_selection")
        self.assertEqual(
            arm["items"], ["Target disease title", "Other coded condition"]
        )

    def test_code_selection_removes_direct_title_cue(self):
        arm = build_arm(self.sample_case(), "code_selection")
        self.assertEqual(arm["items"], ["A001", "B002"])
        self.assertNotIn("Target disease", " ".join(arm["items"]))

    def test_context_only_removes_target_bearing_entry(self):
        arm = build_arm(self.sample_case(), "context_only")
        self.assertEqual(arm["items"], ["Other coded condition"])
        self.assertEqual(arm["target_entry_count"], 1)


if __name__ == "__main__":
    unittest.main()
