import json
from pathlib import Path
from typing import Any, Dict


BASE_DIR = Path(__file__).resolve().parent.parent


SPEC_PATHS = {
    "master_intake_schema": BASE_DIR / "data-model" / "intake" / "master-intake-schema.json",
    "complaint_curation_schema": BASE_DIR / "data-model" / "intake" / "complaint-curation-schema.json",
    "prefill_mapping_spec": BASE_DIR / "data-model" / "intake" / "prefill-mapping-spec.json",
    "scoring_engine_spec": BASE_DIR / "data-model" / "intake" / "scoring-engine-spec.json",
    "upgrade_routing_spec": BASE_DIR / "data-model" / "intake" / "upgrade-routing-spec.json",
    "evidence_vault_spec": BASE_DIR / "data-model" / "intake" / "evidence-vault-spec.json",
    "w9_generator_spec": BASE_DIR / "data-model" / "intake" / "w9-generator-spec.json",
}


class SpecLoaderError(Exception):
    pass


def _read_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise SpecLoaderError(f"Spec file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        raise SpecLoaderError(f"Invalid JSON in spec file: {path} :: {exc}") from exc
    except OSError as exc:
        raise SpecLoaderError(f"Unable to read spec file: {path} :: {exc}") from exc


def get_spec_path(spec_name: str) -> Path:
    path = SPEC_PATHS.get(spec_name)
    if path is None:
        valid = ", ".join(sorted(SPEC_PATHS.keys()))
        raise SpecLoaderError(f"Unknown spec '{spec_name}'. Valid specs: {valid}")
    return path


def load_spec(spec_name: str) -> Dict[str, Any]:
    path = get_spec_path(spec_name)
    return _read_json_file(path)


def load_all_specs() -> Dict[str, Dict[str, Any]]:
    loaded: Dict[str, Dict[str, Any]] = {}
    for spec_name in SPEC_PATHS:
        loaded[spec_name] = load_spec(spec_name)
    return loaded


def validate_all_specs() -> Dict[str, str]:
    results: Dict[str, str] = {}
    for spec_name, path in SPEC_PATHS.items():
        try:
            _read_json_file(path)
            results[spec_name] = "ok"
        except SpecLoaderError as exc:
            results[spec_name] = str(exc)
    return results


if __name__ == "__main__":
    report = validate_all_specs()
    for name, status in report.items():
        print(f"{name}: {status}")
