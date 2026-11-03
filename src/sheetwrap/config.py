"""Job config loading: JSON files layered with "extends"."""
import json
import os
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates"


def _resolve(ref, base):
    """A template ref is a path relative to the referring file, or the name
    of a built-in template (e.g. "shear_check")."""
    p = (base / ref)
    if p.is_file():
        return p
    p = TEMPLATES / (ref if ref.endswith(".json") else ref + ".json")
    if p.is_file():
        return p
    raise FileNotFoundError(f"template not found: {ref}")


def load(path):
    """Load a job config. Keys from "extends" templates are applied first and
    overridden by the file's own keys (shallow merge - lists replace).
    Relative file paths in the result resolve against the job file."""
    path = Path(path).resolve()
    cfg = json.loads(path.read_text(encoding="utf-8"))
    merged = {}
    for ref in cfg.pop("extends", []):
        merged.update(load(_resolve(ref, path.parent)))
    merged.update(cfg)
    merged["_base"] = str(path.parent)
    return merged


def path_of(cfg, key):
    """Resolve a file path setting: env vars expanded, relative to the job
    file. Returns None if unset or the variable was not defined."""
    v = cfg.get(key)
    return resolve(cfg, v) if v else None


def resolve(cfg, v):
    """One path value: env vars expanded, relative to the job file. None if a
    variable was not defined."""
    v = os.path.expandvars(v)
    if "$" in v or "%" in v:
        return None
    return Path(cfg["_base"]) / v
