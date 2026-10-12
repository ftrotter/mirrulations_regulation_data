"""Tests for credential-free Stage 3 YAML configuration."""

from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from mirrulations_markdown.structure_configuration import (  # noqa: E402
    load_structure_configuration,
)
from mirrulations_markdown.structure_models import (  # noqa: E402
    BackwardReference, PassageEnrichment,
)


class StructureConfigurationTest(unittest.TestCase):
    def test_normalizes_structured_reference_description(self):
        result = PassageEnrichment(
            summary="This is a summary.",
            backward_references=[BackwardReference(
                target_key="document:TARGET-1",
                search_description="Look for The seven-day implementation deadline.",
            )],
        )
        self.assertEqual(
            "the seven-day implementation deadline",
            result.backward_references[0].search_description,
        )

    def test_rejects_vague_target_scope_in_search_description(self):
        with self.assertRaisesRegex(ValueError, "vague target scope"):
            BackwardReference(
                target_key="document:TARGET-1",
                search_description="the proposed rule provision on deadlines",
            )
    def test_loads_valid_configuration(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.yaml"
            path.write_text(
                "summary_model: {provider: google, model: flash}\n"
                "reference_model: {provider: google, model: flash}\n",
                encoding="utf-8",
            )
            configuration = load_structure_configuration(configuration_path=path)
            self.assertEqual("google/flash", configuration.summary_model.model_key)

    def test_rejects_credentials_in_yaml(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.yaml"
            path.write_text(
                "api_key: secret\n"
                "summary_model: {provider: google, model: flash}\n"
                "reference_model: {provider: google, model: flash}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "credentials are forbidden"):
                load_structure_configuration(configuration_path=path)

    def test_rejects_different_models_for_combined_call(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "config.yaml"
            path.write_text(
                "summary_model: {provider: google, model: first}\n"
                "reference_model: {provider: google, model: second}\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "must match"):
                load_structure_configuration(configuration_path=path)


if __name__ == "__main__":
    unittest.main(verbosity=2)