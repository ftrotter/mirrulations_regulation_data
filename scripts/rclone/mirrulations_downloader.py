"""Interactively download selected Mirrulations data with rclone."""

import argparse
import datetime
import os
from pathlib import Path
import shlex
import subprocess
import time


BUCKET_REMOTE = "myconfig:mirrulations/"
DEFAULT_TRANSFERS = 50
ENV_FILE_PATH = Path(__file__).with_name(".env")
MIRRULATIONS_DATA_ROOTS = ("raw-data", "derived-data")
TEXT_FILE_PATTERNS = ("*.txt", "*.json", "*.htm")


def parse_comma_separated_values(value):
    """Return nonempty, whitespace-trimmed values from a comma-separated string."""
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_years(year_string):
    """Expand comma-separated years and inclusive year ranges."""
    years = []
    for year_item in parse_comma_separated_values(year_string):
        if "-" not in year_item:
            years.append(int(year_item))
            continue

        range_parts = year_item.split("-")
        if len(range_parts) != 2:
            raise ValueError(f"Invalid year range: {year_item}")
        start_year, end_year = map(int, range_parts)
        if start_year > end_year:
            raise ValueError(
                f"Invalid year range {year_item}: the start year exceeds the end year"
            )
        years.extend(range(start_year, end_year + 1))
    return years


def validate_docket_id(docket_id):
    """Return the agency component from an AGENCY-YEAR-NUMBER docket ID."""
    docket_parts = docket_id.split("-")
    if len(docket_parts) < 3 or not docket_parts[0]:
        raise ValueError(
            f"Invalid docket ID {docket_id!r}; expected AGENCY-YEAR-NUMBER"
        )
    return docket_parts[0]


def build_include_patterns(*, agencies, years, dockets, text_only):
    """Build rclone include filters for the requested Mirrulations selection."""
    file_patterns = TEXT_FILE_PATTERNS if text_only else ("*",)

    # Preserve the original behavior: explicit dockets supersede agency/year
    # filters instead of combining with them.
    if dockets:
        selections = []
        for docket_id in dockets:
            agency = validate_docket_id(docket_id)
            selections.append((agency, docket_id))
    else:
        selected_agencies = agencies or ["*"]
        selected_dockets = [f"*{year}*" for year in years] if years else ["*"]
        selections = [
            (agency, docket_pattern)
            for agency in selected_agencies
            for docket_pattern in selected_dockets
        ]

    include_patterns = []
    for data_root in MIRRULATIONS_DATA_ROOTS:
        for agency, docket_pattern in selections:
            for file_pattern in file_patterns:
                include_patterns.append(
                    f"/{data_root}/{agency}/{docket_pattern}/**/{file_pattern}"
                )
    return include_patterns


def build_rclone_command(
    *, destination_path, rclone_config_file, transfers, include_patterns
):
    """Build an rclone argument list that can be executed without a shell."""
    command = [
        "rclone",
        "copy",
        BUCKET_REMOTE,
        str(destination_path),
        "--config",
        str(rclone_config_file),
        "--checkers",
        str(transfers * 2),
        "--transfers",
        str(transfers),
        "--log-file",
        "rclone.log",
        "--progress",
    ]
    for include_pattern in include_patterns:
        command.extend(("--include", include_pattern))
    return command


def load_environment_file(*, environment_file_path):
    """Load the downloader's .env file after CLI parsing, not during import."""
    if not environment_file_path.is_file():
        raise ValueError(
            "mirrulations_downloader.py Error: .env file not found at "
            f"{environment_file_path}. Copy example.env to .env and configure "
            "MIRRULATIONS_DESTINATION_PATH and RCLONE_CONFIG_FILE."
        )

    try:
        from dotenv import load_dotenv
    except ImportError as import_error:
        raise ValueError(
            "mirrulations_downloader.py Error: python-dotenv is not installed. "
            "Run `pip install -r requirements.txt`."
        ) from import_error

    load_dotenv(environment_file_path)


def get_configured_paths():
    """Validate and return destination and rclone configuration paths."""
    destination_value = os.getenv("MIRRULATIONS_DESTINATION_PATH")
    config_value = os.getenv("RCLONE_CONFIG_FILE")
    errors = []

    destination_path = Path(destination_value).expanduser() if destination_value else None
    if destination_path is None:
        errors.append("MIRRULATIONS_DESTINATION_PATH is not set")
    elif not destination_path.is_dir():
        errors.append(f"destination directory does not exist: {destination_path}")

    rclone_config_file = Path(config_value).expanduser() if config_value else None
    if rclone_config_file is None:
        errors.append("RCLONE_CONFIG_FILE is not set")
    elif not rclone_config_file.is_file():
        errors.append(f"rclone configuration file does not exist: {rclone_config_file}")

    if errors:
        raise ValueError("mirrulations_downloader.py Error: " + "; ".join(errors))
    return destination_path, rclone_config_file


def format_command(command):
    """Return a shell-readable representation of an argument list."""
    return shlex.join(command)


def confirm_and_run_commands(*, commands):
    """Print, confirm, and execute rclone commands."""
    print("Preparing to run:")
    for command in commands:
        print(f"\t{format_command(command)}")

    confirmation = input("Do you want to run these commands? [y/N]: ").strip().lower()
    if confirmation not in {"y", "yes"}:
        print("Not running. Goodbye.")
        return False

    for command in commands:
        print(f"Running:\t{format_command(command)}")
        try:
            subprocess.run(command, check=True)
        except FileNotFoundError as file_not_found_error:
            raise ValueError(
                "mirrulations_downloader.py Error: rclone executable was not found. "
                "Install rclone and ensure it is available on PATH."
            ) from file_not_found_error
    return True


def create_argument_parser():
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Download regulations data from the Mirrulations S3 bucket."
    )
    parser.add_argument(
        "-a", "--agency", default="", help="Agency name(s) separated by commas."
    )
    parser.add_argument(
        "-y",
        "--year",
        default="",
        help="Year(s) or inclusive ranges separated by commas (for example, 2010-2015).",
    )
    parser.add_argument(
        "--textonly",
        action="store_true",
        help="Download only TXT, JSON, and HTM files.",
    )
    parser.add_argument(
        "--getall",
        action="store_true",
        help="Download the entire bucket (cannot be combined with filters).",
    )
    parser.add_argument(
        "--transfers",
        type=int,
        default=DEFAULT_TRANSFERS,
        help=f"Concurrent rclone transfers (default: {DEFAULT_TRANSFERS}).",
    )
    parser.add_argument(
        "-d", "--docket", default="", help="Docket ID(s) separated by commas."
    )
    return parser


def run_downloader(*, arguments):
    """Validate CLI arguments, build the rclone command, and offer to run it."""
    agencies = parse_comma_separated_values(arguments.agency)
    dockets = parse_comma_separated_values(arguments.docket)
    years = parse_years(arguments.year) if arguments.year else []

    if arguments.transfers <= 0:
        raise ValueError(
            "mirrulations_downloader.py Error: --transfers must be greater than zero"
        )

    has_filter = bool(agencies or years or dockets or arguments.textonly)
    if arguments.getall and has_filter:
        raise ValueError(
            "mirrulations_downloader.py Error: --getall cannot be combined with "
            "--agency, --year, --docket, or --textonly"
        )
    if not arguments.getall and not has_filter:
        raise ValueError(
            "mirrulations_downloader.py Error: specify a filter, or use --getall "
            "to download the entire bucket"
        )

    load_environment_file(environment_file_path=ENV_FILE_PATH)
    destination_path, rclone_config_file = get_configured_paths()
    include_patterns = []
    if not arguments.getall:
        include_patterns = build_include_patterns(
            agencies=agencies,
            years=years,
            dockets=dockets,
            text_only=arguments.textonly,
        )

    command = build_rclone_command(
        destination_path=destination_path,
        rclone_config_file=rclone_config_file,
        transfers=arguments.transfers,
        include_patterns=include_patterns,
    )
    start_time = time.monotonic()
    confirm_and_run_commands(commands=[command])
    elapsed_seconds = round(time.monotonic() - start_time)
    print(
        "Process finished!\n"
        f"    Took {datetime.timedelta(seconds=elapsed_seconds)} to finish "
        f"({elapsed_seconds} seconds)"
    )


def main():
    """Run the command-line downloader."""
    parser = create_argument_parser()
    arguments = parser.parse_args()
    try:
        run_downloader(arguments=arguments)
    except (ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"{error}\n")


if __name__ == "__main__":
    main()