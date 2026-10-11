"""Load versioned Stage 3 YAML without credentials."""

from pathlib import Path
import re

import yaml
from pydantic import ValidationError

from .structure_models import StructureConfiguration


SECRET_KEY_PATTERN = re.compile(
    r"(api[_-]?key|secret|token|password|credential)", re.IGNORECASE
)


def _secret_paths(*, value, path=""):
    findings = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            if SECRET_KEY_PATTERN.search(str(key)):
                findings.append(child_path)
            findings.extend(_secret_paths(value=child, path=child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(_secret_paths(value=child, path=f"{path}[{index}]"))
    return findings


def load_structure_configuration(*, configuration_path):
    if not configuration_path.is_file():
        raise ValueError(
            f"structure_configuration.py Error: configuration does not exist: "
            f"{configuration_path}"
        )
    try:
        raw_value = yaml.safe_load(configuration_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(
            f"structure_configuration.py Error: cannot read configuration: {error}"
        ) from error
    if not isinstance(raw_value, dict):
        raise ValueError(
            "structure_configuration.py Error: configuration must be a YAML mapping"
        )
    suspicious_paths = _secret_paths(value=raw_value)
    if suspicious_paths:
        raise ValueError(
            "structure_configuration.py Error: credentials are forbidden in YAML: "
            + ", ".join(suspicious_paths)
        )
    try:
        return StructureConfiguration.model_validate(raw_value)
    except ValidationError as error:
        raise ValueError(
            f"structure_configuration.py Error: invalid configuration: {error}"
        ) from error