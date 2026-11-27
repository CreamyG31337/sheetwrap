"""Job config loading: JSON files layered with "extends" and optional parent site.toml."""
import json
import os
import tomllib
from pathlib import Path

TEMPLATES = Path(__file__).parent / "templates"


def _fallback_roots():
    return [Path.cwd().resolve(), Path(__file__).resolve().parent]


def load_site(start=None):
    """Walk up from `start` (then cwd and package dir) to find `site.toml`.

    Returns `(data_dict, site_dir)` or `({}, None)` when no `site.toml` is found.
    """
    roots = []
    if start is not None:
        roots.append(Path(start).resolve())
    roots.extend(_fallback_roots())
    seen = set()
    for root in roots:
        cur = root if root.is_dir() else root.parent
        for d in (cur, *cur.parents):
            if d in seen:
                continue
            seen.add(d)
            candidate = d / "site.toml"
            if candidate.is_file():
                return tomllib.loads(candidate.read_text(encoding="utf-8-sig")), d
    return {}, None


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


def _load_raw(path):
    path = Path(path).resolve()
    cfg = json.loads(path.read_text(encoding="utf-8"))
    merged = {}
    for ref in cfg.pop("extends", []):
        merged.update(_load_raw(_resolve(ref, path.parent)))
    merged.update(cfg)
    merged["_base"] = str(path.parent)
    return merged


def load(path):
    """Load a job config. Keys from "extends" templates are applied first and
    overridden by the file's own keys (shallow merge - lists replace).
    Missing `company`, `project`, or unresolved `logo` fall back to parent `site.toml`
    (with `company` defaulting to "COMPANY" if still unset).
    Relative file paths in the result resolve against the job file."""
    path = Path(path).resolve()
    merged = _load_raw(path)
    site, site_dir = load_site(path.parent)
    if not merged.get("company"):
        merged["company"] = site.get("company") or "COMPANY"
    if not merged.get("project") and site.get("project"):
        merged["project"] = site["project"]
    if not path_of(merged, "logo") and site.get("logo"):
        site_logo = resolve({"_base": str(site_dir)}, site["logo"])
        if site_logo is not None:
            merged["logo"] = str(site_logo)
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
