"""
Fleet state: line items, point totals, model counts, JSON save/load.

A fleet is a list of entries. Each entry is one roster line (same ship type can appear
on multiple lines with different quantities).

HOW TO ADD SHIPS (data side)
----------------------------
Ship definitions live only in data/ships/<faction>.json — not in this module.
Each ship must have a unique \"id\" across all factions. Hull weapons use
`weapon_mounts` (see `weapon_resolver.py` and `data/weapons.json`). After editing JSON,
restart the Streamlit app or clear cache so loaders refresh.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any


def group_size_bounds(raw: Any) -> tuple[int, int]:
    """
    Parse `group_size` from ship data into inclusive (low, high).

    Supports: int/float; numeric strings ("1"); ranges ("2-4", en/em dash variants).
    Invalid values fall back to (1, 1).
    """
    if raw is None:
        return (1, 1)
    if isinstance(raw, bool):
        return (1, 1)
    if isinstance(raw, (int, float)):
        n = max(1, int(raw))
        return (n, n)
    s = str(raw).strip().replace("–", "-").replace("—", "-")
    if "-" in s:
        left, _, right = s.partition("-")
        try:
            lo = max(1, int(left.strip()))
            hi = max(lo, int(right.strip()))
            return (lo, hi)
        except ValueError:
            return (1, 1)
    try:
        n = max(1, int(float(s)))
        return (n, n)
    except ValueError:
        return (1, 1)


def models_per_fleet_entry(ship: dict[str, Any]) -> int:
    """Models counted per roster line when summing fleet model totals (uses max of a range)."""
    _lo, hi = group_size_bounds(ship.get("group_size"))
    return hi


def _new_entry_id() -> str:
    return str(uuid.uuid4())


@dataclass
class FleetEntry:
    """One roster line: a ship type and how many groups/cards of that type."""

    entry_id: str
    ship_id: str
    quantity: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {"entry_id": self.entry_id, "ship_id": self.ship_id, "quantity": self.quantity}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "FleetEntry":
        return FleetEntry(
            entry_id=str(d["entry_id"]),
            ship_id=str(d["ship_id"]),
            quantity=int(d.get("quantity", 1)),
        )


@dataclass
class Fleet:
    faction_id: str | None = None
    name: str = "Unnamed fleet"
    entries: list[FleetEntry] = field(default_factory=list)

    def add_ship(self, ship_id: str, quantity: int = 1) -> None:
        q = max(1, int(quantity))
        self.entries.append(FleetEntry(entry_id=_new_entry_id(), ship_id=ship_id, quantity=q))

    def remove_entry(self, entry_id: str) -> None:
        self.entries = [e for e in self.entries if e.entry_id != entry_id]

    def clear(self) -> None:
        self.entries.clear()

    def entry_count(self) -> int:
        return len(self.entries)

    def total_models(self, ship_by_id: dict[str, dict[str, Any]]) -> int:
        n = 0
        for e in self.entries:
            ship = ship_by_id.get(e.ship_id)
            if not ship:
                continue
            n += e.quantity * models_per_fleet_entry(ship)
        return n

    def total_points(self, ship_by_id: dict[str, dict[str, Any]]) -> int:
        pts = 0
        for e in self.entries:
            ship = ship_by_id.get(e.ship_id)
            if not ship:
                continue
            p = int(ship.get("points", 0) or 0)
            pts += p * e.quantity
        return pts

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": "ttsg_fleet_v1",
            "name": self.name,
            "faction_id": self.faction_id,
            "entries": [e.to_dict() for e in self.entries],
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Fleet":
        entries_raw = d.get("entries") or []
        entries = [FleetEntry.from_dict(x) for x in entries_raw if isinstance(x, dict)]
        return Fleet(
            faction_id=d.get("faction_id"),
            name=str(d.get("name") or "Imported fleet"),
            entries=entries,
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @staticmethod
    def from_json(text: str) -> "Fleet":
        data = json.loads(text)
        return Fleet.from_dict(data)


def summarize_line(ship: dict[str, Any] | None, entry: FleetEntry) -> str:
    if not ship:
        return f"{entry.quantity}× (unknown ship {entry.ship_id})"
    name = ship.get("name", entry.ship_id)
    return f"{entry.quantity}× {name} — {ship.get('class', '?')} — {ship.get('points', 0)} pts each"
