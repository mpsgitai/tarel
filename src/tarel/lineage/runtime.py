"""Load and validate runtime lineage inputs and documents."""

from __future__ import annotations

import json
from pathlib import Path

from tarel.lineage._runtime_parse import (
    DOCUMENT_VERSION,
    DOCUMENT_VERSION_V2,
    DOCUMENT_VERSION_V3,
    INPUT_VERSION,
    INPUT_VERSION_V2,
    INPUT_VERSION_V3,
    require_object,
    unique_object,
)
from tarel.lineage.contracts import LineageFailure
from tarel.lineage.runtime_records import RuntimeLineageDocument, RuntimeLineageInput


def load_runtime_lineage_input(path: Path) -> RuntimeLineageInput:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except FileNotFoundError as exc:
        raise LineageFailure(
            "runtime_lineage_input_not_found",
            "Runtime input file not found.",
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LineageFailure(
            "invalid_runtime_lineage",
            "Could not read runtime input JSON.",
        ) from exc
    return RuntimeLineageInput.from_dict(require_object(payload, "runtime input"))


def validate_runtime_lineage_input(value: RuntimeLineageInput) -> None:
    RuntimeLineageInput.from_dict(value.to_dict())


def validate_runtime_lineage_document(value: RuntimeLineageDocument) -> None:
    RuntimeLineageDocument.from_dict(value.to_dict())


def runtime_lineage_document_version(input_contract_version: str) -> str:
    versions = {
        INPUT_VERSION: DOCUMENT_VERSION,
        INPUT_VERSION_V2: DOCUMENT_VERSION_V2,
        INPUT_VERSION_V3: DOCUMENT_VERSION_V3,
    }
    try:
        return versions[input_contract_version]
    except KeyError as exc:
        raise LineageFailure(
            "unsupported_runtime_lineage",
            "Unsupported TAREL runtime-lineage input contract.",
        ) from exc
