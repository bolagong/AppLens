"""Regression tests for the safe bulk-adoption workbench flow."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from generate_flutter import DART_TEMPLATE, prototype_payload  # noqa: E402
from generate_prd import build_prd  # noqa: E402
from model_tools import ABSTRACT_ADOPTION_NOTE, adopt_all_abstract_features, display_feature_name  # noqa: E402


class WorkbenchTests(unittest.TestCase):
    def test_bulk_adoption_marks_every_function_as_original_abstract_feature(self) -> None:
        model = {
            "project": {"status": "evidence_review"},
            "functions": [
                {"name": "Search", "product_decision": "modify", "modification_notes": "Requires product-owner review."},
                {"name": "Settings", "product_decision": "add", "modification_notes": ""},
            ],
            "generation": {
                "approved_model_version": "v1.0",
                "approved_at": "yesterday",
                "approved_model_fingerprint": "old",
                "prd_status": "ready_to_generate",
            },
            "audit": [],
        }

        count, changed = adopt_all_abstract_features(model)

        self.assertEqual(count, 2)
        self.assertTrue(changed)
        self.assertEqual(model["project"]["status"], "model_review")
        self.assertTrue(all(item["product_decision"] == "keep" for item in model["functions"]))
        self.assertTrue(all(item["modification_notes"] == ABSTRACT_ADOPTION_NOTE for item in model["functions"]))
        self.assertIsNone(model["generation"]["approved_model_version"])
        self.assertEqual(model["audit"][-1]["event"], "all_abstract_features_adopted")

        count, changed = adopt_all_abstract_features(model)
        self.assertEqual(count, 2)
        self.assertFalse(changed)

    def test_workbench_has_bulk_action_without_per_function_decision_controls(self) -> None:
        html = (Path(__file__).resolve().parents[1] / "workbench" / "index.html").read_text(encoding="utf-8")

        self.assertIn('id="adoptAllButton"', html)
        self.assertIn("一键采用全部抽象功能", html)
        self.assertIn('id="previewPanel"', html)
        self.assertIn('class="workspace-column"', html)
        self.assertIn('class="phone-frame"', html)
        self.assertIn("width: 390px", html)
        self.assertIn("overflow-y: auto", html)
        self.assertIn("touch-action: pan-y", html)
        self.assertIn('class="app-bottom-nav"', html)
        self.assertIn('id="previewSearch"', html)
        self.assertIn("Northstar", html)
        self.assertIn("原创成果预览", html)
        self.assertNotIn('id="addFunction"', html)
        self.assertNotIn('id="deleteFunction"', html)
        self.assertNotIn('id="decision"', html)
        self.assertNotIn("decisionLabels", html)

    def test_generators_use_original_abstract_feature_language(self) -> None:
        model = {
            "project": {"name": "Original reference", "analysis_scope": "Product reference only"},
            "visual_model": {"reference_notes": [], "decisions": {}},
            "generation": {"approved_model_version": "v1.0"},
            "functions": [{"name": "Search", "product_decision": "keep", "confidence": "static_inference"}],
        }

        payload = prototype_payload(model)
        prd = build_prd(model)

        self.assertNotIn("decision", payload["functions"][0])
        self.assertNotIn("ChoiceChip", DART_TEMPLATE)
        self.assertNotIn("modify", DART_TEMPLATE)
        self.assertIn("采用方式：全部抽象功能均以原创实现采用", prd)
        self.assertNotIn("产品决策：", prd)

    def test_feature_names_have_chinese_user_facing_labels(self) -> None:
        self.assertEqual(display_feature_name("Search"), "搜索")
        self.assertEqual(display_feature_name("Settings"), "设置")
        self.assertEqual(display_feature_name("搜索"), "搜索")


if __name__ == "__main__":
    unittest.main()
