"""Unit tests for the rclone Mirrulations downloader."""

import importlib.util
from pathlib import Path
import unittest
from unittest import mock


DOWNLOADER_PATH = (
    Path(__file__).parents[1] / "scripts" / "rclone" / "mirrulations_downloader.py"
)
MODULE_SPEC = importlib.util.spec_from_file_location(
    "mirrulations_downloader", DOWNLOADER_PATH
)
downloader = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(downloader)


class ParseYearsTest(unittest.TestCase):
    def test_expands_lists_and_ranges(self):
        self.assertEqual(
            [2010, 2012, 2013, 2014],
            downloader.parse_years("2010,2012-2014"),
        )

    def test_rejects_descending_range(self):
        with self.assertRaisesRegex(ValueError, "start year exceeds"):
            downloader.parse_years("2024-2020")


class IncludePatternTest(unittest.TestCase):
    def test_agency_filter_covers_both_data_roots(self):
        patterns = downloader.build_include_patterns(
            agencies=["DEA"], years=[], dockets=[], text_only=False
        )
        self.assertEqual(
            ["/raw-data/DEA/*/**/*", "/derived-data/DEA/*/**/*"], patterns
        )

    def test_year_and_text_filters_cover_all_agencies_and_text_types(self):
        patterns = downloader.build_include_patterns(
            agencies=[], years=[2022], dockets=[], text_only=True
        )
        self.assertEqual(8, len(patterns))
        self.assertIn("/raw-data/*/*2022*/**/*.txt", patterns)
        self.assertIn("/raw-data/*/*2022*/**/*.json", patterns)
        self.assertIn("/raw-data/*/*2022*/**/*.htm", patterns)
        self.assertIn("/raw-data/*/*2022*/**/*.html", patterns)
        self.assertIn("/derived-data/*/*2022*/**/*.txt", patterns)

    def test_docket_filter_supersedes_agency_and_year(self):
        patterns = downloader.build_include_patterns(
            agencies=["EPA"],
            years=[2020],
            dockets=["DEA-2024-0059"],
            text_only=False,
        )
        self.assertEqual(
            [
                "/raw-data/DEA/DEA-2024-0059/**/*",
                "/derived-data/DEA/DEA-2024-0059/**/*",
            ],
            patterns,
        )

    def test_rejects_invalid_docket_id(self):
        with self.assertRaisesRegex(ValueError, "Invalid docket ID"):
            downloader.build_include_patterns(
                agencies=[], years=[], dockets=["INVALID"], text_only=False
            )


class RcloneCommandTest(unittest.TestCase):
    def test_builds_argument_list_with_filters(self):
        command = downloader.build_rclone_command(
            destination_path=Path("/destination with spaces"),
            rclone_config_file=Path("/config with spaces/rclone.config"),
            transfers=25,
            include_patterns=["/raw-data/DEA/*/**/*"],
        )
        self.assertEqual("rclone", command[0])
        self.assertEqual("myconfig:mirrulations/", command[2])
        self.assertIn("/destination with spaces", command)
        self.assertIn("50", command)
        self.assertEqual(["--include", "/raw-data/DEA/*/**/*"], command[-2:])

    def test_get_all_command_has_no_include_filters(self):
        command = downloader.build_rclone_command(
            destination_path=Path("/data"),
            rclone_config_file=Path("/rclone.config"),
            transfers=50,
            include_patterns=[],
        )
        self.assertNotIn("--include", command)


class CommandExecutionTest(unittest.TestCase):
    @mock.patch("builtins.input", return_value="no")
    @mock.patch.object(downloader.subprocess, "run")
    def test_declined_confirmation_does_not_run_command(
        self, subprocess_run, _input
    ):
        did_run = downloader.confirm_and_run_commands(commands=[["rclone", "copy"]])
        self.assertFalse(did_run)
        subprocess_run.assert_not_called()

    @mock.patch("builtins.input", return_value="yes")
    @mock.patch.object(downloader.subprocess, "run")
    def test_confirmation_runs_argument_list_without_shell(
        self, subprocess_run, _input
    ):
        command = ["rclone", "copy", "source", "/destination with spaces"]
        did_run = downloader.confirm_and_run_commands(commands=[command])
        self.assertTrue(did_run)
        subprocess_run.assert_called_once_with(command, check=True)

    @mock.patch("builtins.input", return_value="yes")
    @mock.patch.object(downloader.subprocess, "run", side_effect=FileNotFoundError)
    def test_missing_rclone_has_specific_error(self, _subprocess_run, _input):
        with self.assertRaisesRegex(ValueError, "rclone executable was not found"):
            downloader.confirm_and_run_commands(commands=[["rclone", "copy"]])


class ArgumentValidationTest(unittest.TestCase):
    def setUp(self):
        self.parser = downloader.create_argument_parser()

    def test_requires_filter_or_get_all(self):
        arguments = self.parser.parse_args([])
        with self.assertRaisesRegex(ValueError, "specify a filter"):
            downloader.run_downloader(arguments=arguments)

    def test_get_all_rejects_filters(self):
        arguments = self.parser.parse_args(["--getall", "--agency", "DEA"])
        with self.assertRaisesRegex(ValueError, "cannot be combined"):
            downloader.run_downloader(arguments=arguments)

    def test_rejects_nonpositive_transfer_count(self):
        arguments = self.parser.parse_args(["--agency", "DEA", "--transfers", "0"])
        with self.assertRaisesRegex(ValueError, "greater than zero"):
            downloader.run_downloader(arguments=arguments)

    def test_path_overrides_must_be_provided_together(self):
        arguments = self.parser.parse_args(
            ["--docket", "CMS-2026-1255", "--textonly", "--destination", "/tmp/data"]
        )
        with self.assertRaisesRegex(ValueError, "must be provided together"):
            downloader.run_downloader(arguments=arguments)

    @mock.patch.object(downloader, "confirm_and_run_commands", return_value=True)
    def test_explicit_paths_bypass_environment_file(self, confirm_commands):
        with mock.patch.object(Path, "mkdir"), mock.patch.object(
            Path, "is_file", return_value=True
        ):
            arguments = self.parser.parse_args(
                [
                    "--docket", "CMS-2026-1255", "--textonly",
                    "--destination", "/tmp/source", "--rclone-config",
                    "/tmp/rclone.config", "--yes",
                ]
            )
            downloader.run_downloader(arguments=arguments)
        self.assertTrue(confirm_commands.call_args.kwargs["assume_yes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)