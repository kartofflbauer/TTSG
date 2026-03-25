"""
Fleet composition validation — rules are data-driven where possible.

Extend validate_fleet() with new checks as your ruleset grows. Keep thresholds in
data/game_config.json or a dedicated rules JSON file so balance passes do not require
Python edits for simple limit changes.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fleet import Fleet


def validate_fleet(
    fleet: Fleet,
    ship_by_id: dict[str, dict[str, Any]],
    game_config: dict[str, Any],
) -> list[str]:
    """
    Return human-readable warnings (empty list = no issues detected).
    """
    warnings: list[str] = []

    if fleet.faction_id:
        for e in fleet.entries:
            ship = ship_by_id.get(e.ship_id)
            if ship and str(ship.get("faction")) != str(fleet.faction_id):
                warnings.append(
                    f"Entry uses ship \"{ship.get('name', e.ship_id)}\" from faction "
                    f'"{ship.get("faction")}", but fleet is set to "{fleet.faction_id}".'
                )

    unknown = [e.ship_id for e in fleet.entries if e.ship_id not in ship_by_id]
    if unknown:
        warnings.append(f"Unknown ship id(s) in fleet (missing from data): {', '.join(unknown)}")

    max_pts = game_config.get("max_fleet_points")
    if max_pts is not None:
        try:
            cap = int(max_pts)
            current = fleet.total_points(ship_by_id)
            if current > cap:
                warnings.append(f"Fleet exceeds points cap: {current} / {cap}")
        except (TypeError, ValueError):
            pass

    for e in fleet.entries:
        if e.quantity < 1:
            warnings.append(f"Invalid quantity ({e.quantity}) for ship id \"{e.ship_id}\".")

    # Example heuristic: warn on many duplicate entries of the same id (often a mistake)
    counts = Counter(e.ship_id for e in fleet.entries)
    for sid, c in counts.items():
        if c > 5:
            ship = ship_by_id.get(sid, {})
            nm = ship.get("name", sid)
            warnings.append(f"Many separate lines for \"{nm}\" ({c} entries) — merge quantities?")

    # Class spread hint (optional soft check)
    class_counts: Counter[str] = Counter()
    for e in fleet.entries:
        ship = ship_by_id.get(e.ship_id)
        if not ship:
            continue
        cls = str(ship.get("class", "Unknown"))
        class_counts[cls] += e.quantity
    if len(class_counts) == 1 and fleet.entry_count() > 1:
        warnings.append("Fleet contains only one ship class — intentional?")

    return warnings
