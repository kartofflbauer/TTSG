"""
Load TTSG ship rosters and game config from local JSON.

HOW TO ADD A NEW FACTION
------------------------
1. Create a new file under data/ships/, e.g. data/ships/scourge.json
2. Use the same top-level shape as ucm.json / phr.json:
   - faction_id: short machine id (folder-safe, used in ship records)
   - faction_name: display name in the UI
   - ships: list of ship objects (see HOW TO ADD SHIPS in sample JSON or fleet comments)
3. No code changes required: all *.json files in data/ships/ are loaded automatically.

Optional: adjust data/game_config.json for global limits (e.g. max fleet points).

SHARED WEAPONS
--------------
- Edit `data/weapons.json` for library entries (id, name, lock, attacks, damage, ap, notes, optional keywords).
- Ships reference library guns via `weapon_mounts` on each hull (see `weapon_resolver.py`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def project_root() -> Path:
    """
    Directory that contains `data/ships/` (and `data/weapons.json`).

    Resolves from this file upward so publishing still works when Python modules live in a
    subfolder (e.g. `src/`) but `data/` sits at the repo root — a common Streamlit Cloud layout.
    """
    here = Path(__file__).resolve().parent
    for p in (here, *here.parents):
        if (p / "data" / "ships").is_dir():
            return p
    return here


_ROOT = project_root()
_SHIPS_DIR = _ROOT / "data" / "ships"
_CONFIG_PATH = _ROOT / "data" / "game_config.json"
_WEAPONS_PATH = _ROOT / "data" / "weapons.json"


def debug_data_loading_state() -> dict[str, Any]:
    """For troubleshooting deploys: paths, existence, discovered JSON under data/ships."""
    ships = _ROOT / "data" / "ships"
    files: list[str] = []
    if ships.is_dir():
        files = sorted(p.name for p in ships.glob("*.json"))
    return {
        "project_root": str(_ROOT),
        "data_loader_dir": str(Path(__file__).resolve().parent),
        "ships_dir": str(ships),
        "ships_dir_is_dir": ships.is_dir(),
        "ship_json_files": files,
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_game_config() -> dict[str, Any]:
    if not _CONFIG_PATH.is_file():
        return {"max_fleet_points": None}
    return _read_json(_CONFIG_PATH)


def load_weapons_library() -> dict[str, dict[str, Any]]:
    """
    weapon_id -> weapon definition. Ships use these ids in weapon_mounts[].weapon_id.

    File format: { "weapons": [ { "id": "...", ... }, ... ] }
    """
    if not _WEAPONS_PATH.is_file():
        return {}
    data = _read_json(_WEAPONS_PATH)
    raw = data.get("weapons")
    out: dict[str, dict[str, Any]] = {}
    if isinstance(raw, list):
        for w in raw:
            if isinstance(w, dict) and w.get("id"):
                out[str(w["id"])] = w
    elif isinstance(raw, dict):
        for k, w in raw.items():
            if isinstance(w, dict):
                out[str(k)] = w
    return out


def load_faction_files() -> dict[str, dict[str, Any]]:
    """
    Returns mapping faction_id -> {faction_name, ships: [...]}.
    """
    if not _SHIPS_DIR.is_dir():
        return {}

    result: dict[str, dict[str, Any]] = {}
    for path in sorted(_SHIPS_DIR.glob("*.json")):
        data = _read_json(path)
        fid = data.get("faction_id")
        if not fid:
            continue
        result[str(fid)] = {
            "faction_name": data.get("faction_name", str(fid).upper()),
            "ships": data.get("ships") or [],
            "_source_file": path.name,
        }
    return result


def build_ship_index(by_faction: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """ship_id -> ship dict (includes faction for convenience)."""
    index: dict[str, dict[str, Any]] = {}
    for fid, pack in by_faction.items():
        for ship in pack.get("ships", []):
            sid = ship.get("id")
            if not sid:
                continue
            merged = {**ship, "faction": ship.get("faction", fid)}
            index[str(sid)] = merged
    return index


def list_faction_options(by_faction: dict[str, dict[str, Any]]) -> list[tuple[str, str]]:
    """[(faction_id, display_name), ...] sorted by display name."""
    opts: list[tuple[str, str]] = []
    for fid, pack in by_faction.items():
        name = pack.get("faction_name", fid)
        opts.append((fid, str(name)))
    opts.sort(key=lambda x: x[1].lower())
    return opts
