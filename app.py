"""
TTSG Fleetbuilder — Streamlit UI.

Run from project root:
    streamlit run app.py
    (If `streamlit` is not on PATH: python -m streamlit run app.py)

After editing JSON data files, use Streamlit's "Clear cache" (menu) or restart the
server so @st.cache_data reloads rosters.

UI logic only: ship definitions and balance live in data/ and are loaded via data_loader.
Fleet operations use fleet.py; warnings use validation.py.
"""

from __future__ import annotations

import streamlit as st

from data_loader import (
    build_ship_index,
    debug_data_loading_state,
    list_faction_options,
    load_faction_files,
    load_game_config,
    load_weapons_library,
)
from fleet import Fleet, summarize_line
from validation import validate_fleet
from weapon_resolver import format_resolved_weapon_line, resolve_ship_weapon_mounts


@st.cache_data
def _cached_factions() -> dict:
    return load_faction_files()


@st.cache_data
def _cached_config() -> dict:
    return load_game_config()


@st.cache_data
def _cached_weapons() -> dict:
    return load_weapons_library()


def _ensure_session() -> None:
    if "fleet" not in st.session_state:
        st.session_state.fleet = Fleet()
    if "selected_faction" not in st.session_state:
        st.session_state.selected_faction = None


def _ships_for_faction(by_faction: dict, faction_id: str) -> list[dict]:
    pack = by_faction.get(faction_id) or {}
    return list(pack.get("ships") or [])


def _filter_ships(
    ships: list[dict],
    search: str,
    class_pick: str | None,
    tonnage_pick: str | None,
    tag_pick: str | None,
) -> list[dict]:
    out = ships
    if search.strip():
        q = search.strip().lower()
        out = [
            s
            for s in out
            if q in str(s.get("name", "")).lower()
            or q in str(s.get("id", "")).lower()
            or any(q in str(t).lower() for t in (s.get("tags") or []))
        ]
    if class_pick and class_pick != "(any)":
        out = [s for s in out if str(s.get("class")) == class_pick]
    if tonnage_pick and tonnage_pick != "(any)":
        out = [s for s in out if str(s.get("tonnage")) == tonnage_pick]
    if tag_pick and tag_pick != "(any)":
        out = [s for s in out if tag_pick in (s.get("tags") or [])]
    return out


def _all_tags(ships: list[dict]) -> list[str]:
    tags: set[str] = set()
    for s in ships:
        for t in s.get("tags") or []:
            tags.add(str(t))
    return sorted(tags, key=str.lower)


def _all_values(ships: list[dict], key: str) -> list[str]:
    vals = {str(s.get(key)) for s in ships if s.get(key) is not None}
    return sorted(vals, key=str.lower)


def main() -> None:
    st.set_page_config(page_title="TTSG Fleetbuilder", layout="wide")
    _ensure_session()

    by_faction = _cached_factions()
    game_config = _cached_config()
    weapon_by_id = _cached_weapons()
    ship_by_id = build_ship_index(by_faction)
    faction_opts = list_faction_options(by_faction)

    if not faction_opts:
        st.error(
            "No faction data found. The app looks for `data/ships/*.json` with a top-level "
            "`faction_id` field."
        )
        with st.expander("Deploy debug (paths)", expanded=True):
            st.json(debug_data_loading_state())
        st.info(
            "**Common fix on Streamlit Cloud:** set **Main file path** to the `app.py` that sits "
            "**next to** the `data/` folder (same folder as `data_loader.py`). If you moved code "
            "under `src/` but left `data/` at the repo root, redeploy after pulling the latest "
            "changes — paths are resolved by walking up to the folder that contains `data/ships/`."
        )
        st.stop()

    st.title("TTSG Fleetbuilder")
    #st.caption(
    #    "Data-driven roster builder — ships in `data/ships/`, shared weapons in `data/weapons.json`, "
    #    "mounts per hull reference weapons by id (see `weapon_resolver.py`)."
    #)

    fleet: Fleet = st.session_state.fleet

    with st.sidebar:
        st.header("Faction")
        labels = [f"{name} ({fid})" for fid, name in faction_opts]
        ids = [fid for fid, _ in faction_opts]
        default_idx = 0
        if st.session_state.selected_faction in ids:
            default_idx = ids.index(st.session_state.selected_faction)
        choice = st.selectbox("Active faction", options=range(len(labels)), format_func=lambda i: labels[i], index=default_idx)
        faction_id = ids[choice]
        st.session_state.selected_faction = faction_id
        fleet.faction_id = faction_id

        st.divider()
        st.subheader("Load / save")
        uploaded = st.file_uploader("Load fleet JSON", type=["json"])
        if uploaded is not None:
            try:
                text = uploaded.read().decode("utf-8")
                loaded = Fleet.from_json(text)
                st.session_state.fleet = loaded
                if loaded.faction_id and loaded.faction_id in dict(faction_opts):
                    st.session_state.selected_faction = loaded.faction_id
                st.success("Fleet loaded.")
                st.rerun()
            except Exception as ex:  # noqa: BLE001 — show user-facing parse errors
                st.error(f"Could not load file: {ex}")

        json_text = fleet.to_json()
        st.download_button(
            "Download fleet JSON",
            data=json_text,
            file_name="ttsg_fleet.json",
            mime="application/json",
        )

        st.divider()
        st.subheader("Browse filters")
        roster = _ships_for_faction(by_faction, faction_id)
        search = st.text_input("Search name, id, or tag", value="")
        classes = ["(any)"] + _all_values(roster, "class")
        tonnages = ["(any)"] + _all_values(roster, "tonnage")
        tags = ["(any)"] + _all_tags(roster)
        c1, c2 = st.columns(2)
        with c1:
            class_pick = st.selectbox("Class", classes)
        with c2:
            tonnage_pick = st.selectbox("Tonnage", tonnages)
        tag_pick = st.selectbox("Tag", tags)

    filtered = _filter_ships(roster, search, class_pick, tonnage_pick, tag_pick)

    left, right = st.columns((1.1, 1.0))

    with left:
        st.subheader("Available ships")
        st.write(f"Showing **{len(filtered)}** of **{len(roster)}** ships for **{faction_id.upper()}**.")
        if not filtered:
            st.info("No ships match filters.")
        for ship in filtered:
            sid = ship["id"]
            with st.expander(f"{ship.get('name', sid)} — {ship.get('class', '')} — {ship.get('points', 0)} pts"):
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Tonnage", ship.get("tonnage", "—"))
                m2.metric("Group size", ship.get("group_size", "—"))
                m3.metric("Hull", ship.get("hull", "—"))
                m4.metric("Thrust", ship.get("thrust", "—"))
                st.write(
                    f"**Scan** {ship.get('scan', '—')} · **Sig** {ship.get('signature', '—')} · "
                    f"**PD** {ship.get('pd', '—')} · **Evasion** {ship.get('evasion', '—')}"
                )
                st.write("**Shields:**", ship.get("shields", {}))
                st.write("**Armor:**", ship.get("armor", {}))
                resolved = resolve_ship_weapon_mounts(ship, weapon_by_id)
                if resolved:
                    st.write("**Weapons (resolved):**")
                    for rw in resolved:
                        st.write(f"- {format_resolved_weapon_line(rw)}")
                if ship.get("special_rules"):
                    st.write("**Special:**", ", ".join(str(x) for x in ship["special_rules"]))
                if ship.get("tags"):
                    st.write("**Tags:**", ", ".join(str(t) for t in ship["tags"]))
                qty = st.number_input("Quantity", min_value=1, max_value=12, value=1, key=f"qty_{sid}")
                if st.button("Add to fleet", key=f"add_{sid}"):
                    fleet.add_ship(sid, quantity=int(qty))
                    st.rerun()

    with right:
        st.subheader("Fleet")
        pts = fleet.total_points(ship_by_id)
        models = fleet.total_models(ship_by_id)
        ec = fleet.entry_count()
        cap = game_config.get("max_fleet_points")
        cap_str = str(cap) if cap is not None else "—"
        k1, k2, k3 = st.columns(3)
        k1.metric("Fleet points", f"{pts} / {cap_str}")
        k2.metric("Fleet entries", ec)
        k3.metric("Ship models", models)

        fname = st.text_input("Fleet name", value=fleet.name, key="fleet_name_input")
        fleet.name = fname

        warnings = validate_fleet(fleet, ship_by_id, game_config)
        if warnings:
            st.warning("**Validation**")
            for w in warnings:
                st.write(f"- {w}")
        else:
            st.success("No validation warnings.")

        st.divider()
        st.markdown("**Summary**")
        if not fleet.entries:
            st.caption("Fleet is empty — add ships from the left.")
        for entry in fleet.entries:
            ship = ship_by_id.get(entry.ship_id)
            line = summarize_line(ship, entry)
            c_a, c_b = st.columns((4, 1))
            with c_a:
                st.write(line)
            with c_b:
                if st.button("Remove", key=f"rm_{entry.entry_id}"):
                    fleet.remove_entry(entry.entry_id)
                    st.rerun()

        if fleet.entries and st.button("Clear fleet"):
            fleet.clear()
            st.rerun()


if __name__ == "__main__":
    main()
