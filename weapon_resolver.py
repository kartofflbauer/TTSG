"""
Resolve ship weapon mounts into display-ready profiles.

Ships list `weapon_mounts` on the hull. Each mount either:
  - references `data/weapons.json` by `weapon_id` and applies optional `overrides` / arc /
    `added_keywords`, or
  - sets `inline_weapon` for a one-off profile (no library row).

Balance workflow: tune shared guns in `data/weapons.json`; tune per-hull fit in the
ship file (mount count, arc, small overrides). Rare systems use `inline_weapon` only.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResolvedWeapon:
    """Final profile for UI or export after library + mount merge."""

    mount_name: str
    count: int
    arc: list[str]
    name: str
    lock: Any | None = None
    attacks: Any | None = None
    damage: Any | None = None
    ap: Any | None = None
    notes: str | None = None
    keywords: list[str] = field(default_factory=list)
    weapon_id: str | None = None
    source: str = "library"  # "library" | "inline"

    def to_display_dict(self) -> dict[str, Any]:
        return {
            "mount_name": self.mount_name,
            "count": self.count,
            "arc": self.arc,
            "name": self.name,
            "lock": self.lock,
            "attacks": self.attacks,
            "damage": self.damage,
            "ap": self.ap,
            "notes": self.notes,
            "keywords": self.keywords,
            "weapon_id": self.weapon_id,
            "source": self.source,
        }


def _normalize_arc(arc: Any) -> list[str]:
    if arc is None:
        return []
    if isinstance(arc, str):
        return [arc]
    if isinstance(arc, list):
        return [str(a) for a in arc]
    return [str(arc)]


def _merge_keywords(base: list[str] | None, added: list[str] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for src in (base or [], added or []):
        for k in src:
            ks = str(k)
            if ks not in seen:
                seen.add(ks)
                out.append(ks)
    return out


def _apply_overrides(base: dict[str, Any], overrides: dict[str, Any] | None) -> dict[str, Any]:
    if not overrides:
        return deepcopy(base)
    merged = deepcopy(base)
    for k, v in overrides.items():
        if k in ("weapon_id", "mount_name", "count", "arc", "added_keywords", "inline_weapon"):
            continue
        merged[k] = v
    return merged


def resolve_weapon_mount(
    mount: dict[str, Any],
    weapon_by_id: dict[str, dict[str, Any]],
) -> ResolvedWeapon:
    """
    Combine one mount dict with the weapon library (or inline base) into ResolvedWeapon.
    Unknown weapon_id yields a warning string in notes rather than raising (data-friendly).
    """
    mount_name = str(mount.get("mount_name") or "Mount")
    count = int(mount.get("count", 1) or 1)
    arc = _normalize_arc(mount.get("arc"))
    added_kw = [str(x) for x in (mount.get("added_keywords") or [])]
    overrides = mount.get("overrides")
    if overrides is not None and not isinstance(overrides, dict):
        overrides = {}

    inline = mount.get("inline_weapon")
    wid = mount.get("weapon_id")

    if inline is not None and isinstance(inline, dict):
        base = deepcopy(inline)
        base = _apply_overrides(base, overrides)
        name = str(base.get("name") or mount_name)
        raw_kw = base.get("keywords")
        kw_from_base = [str(x) for x in raw_kw] if isinstance(raw_kw, list) else []
        kw = _merge_keywords(kw_from_base, added_kw)
        arc_out = arc if arc else _normalize_arc(base.get("arc"))
        return ResolvedWeapon(
            mount_name=mount_name,
            count=max(1, count),
            arc=arc_out,
            name=name,
            lock=base.get("lock"),
            attacks=base.get("attacks"),
            damage=base.get("damage"),
            ap=base.get("ap"),
            notes=base.get("notes"),
            keywords=kw,
            weapon_id=None,
            source="inline",
        )

    if not wid:
        return ResolvedWeapon(
            mount_name=mount_name,
            count=max(1, count),
            arc=arc,
            name=mount_name,
            lock=None,
            attacks=None,
            damage=None,
            ap=None,
            notes="Invalid mount: set weapon_id or inline_weapon",
            keywords=added_kw,
            weapon_id=None,
            source="inline",
        )

    lib = weapon_by_id.get(str(wid))
    if not lib:
        return ResolvedWeapon(
            mount_name=mount_name,
            count=max(1, count),
            arc=arc,
            name=str(wid),
            lock=None,
            attacks=None,
            damage=None,
            ap=None,
            notes=f"Unknown weapon_id: {wid}",
            keywords=added_kw,
            weapon_id=str(wid),
            source="library",
        )

    merged = {
        "name": lib.get("name"),
        "lock": lib.get("lock"),
        "attacks": lib.get("attacks"),
        "damage": lib.get("damage"),
        "ap": lib.get("ap"),
        "notes": lib.get("notes"),
        "keywords": list(lib.get("keywords") or []),
    }
    merged = _apply_overrides(merged, overrides)
    kw = _merge_keywords([str(x) for x in merged.get("keywords") or []], added_kw)

    return ResolvedWeapon(
        mount_name=mount_name,
        count=max(1, count),
        arc=arc,
        name=str(merged.get("name") or wid),
        lock=merged.get("lock"),
        attacks=merged.get("attacks"),
        damage=merged.get("damage"),
        ap=merged.get("ap"),
        notes=merged.get("notes"),
        keywords=kw,
        weapon_id=str(wid),
        source="library",
    )


def resolve_ship_weapon_mounts(
    ship: dict[str, Any],
    weapon_by_id: dict[str, dict[str, Any]],
) -> list[ResolvedWeapon]:
    mounts = ship.get("weapon_mounts") or []
    if not isinstance(mounts, list):
        return []
    return [resolve_weapon_mount(m, weapon_by_id) for m in mounts if isinstance(m, dict)]


def format_resolved_weapon_line(r: ResolvedWeapon) -> str:
    """Single-line summary for lists and tables."""
    arc_s = "/".join(r.arc) if r.arc else "—"
    bits = [
        f"{r.count}× {r.mount_name}",
        f"({r.name})",
        f"arc {arc_s}",
    ]
    stats = []
    if r.lock is not None:
        stats.append(f"Lk{r.lock}")
    if r.attacks is not None:
        stats.append(f"Atk{r.attacks}")
    if r.damage is not None:
        stats.append(f"Dam{r.damage}")
    if r.ap is not None:
        stats.append(f"AP{r.ap}")
    if stats:
        bits.append("[" + " ".join(stats) + "]")
    if r.keywords:
        bits.append("{" + ", ".join(r.keywords) + "}")
    if r.notes:
        bits.append(f"— {r.notes}")
    return " ".join(bits)
