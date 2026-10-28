"""Ensure synthetic user references used by imported tickets exist."""
import json
from pathlib import Path


def main():
    data_dir = Path(__file__).resolve().parents[1] / "data"
    specs = {
        "users.json": ("reported_by_id", "affected_person_id", "owner_id"),
        "assets.json": ("asset_id",),
        "configuration_items.json": ("configuration_item_id",),
    }
    referenced = set()
    for filename in ("historical_tickets.json", "sample_open_tickets.json"):
        for ticket in json.loads((data_dir / filename).read_text(encoding="utf-8-sig")):
            for field in ("reported_by_id", "affected_person_id", "owner_id", "asset_id", "configuration_item_id"):
                if ticket.get(field): referenced.add(ticket[field])
    for filename, fields in specs.items():
        path = data_dir / filename
        rows = json.loads(path.read_text(encoding="utf-8-sig"))
        by_id = {row["id"]: row for row in rows}
        prefix = "USR-" if filename == "users.json" else "ASSET-" if filename == "assets.json" else "CI-"
        for identifier in sorted(referenced):
            if identifier.startswith(prefix) and identifier not in by_id:
                by_id[identifier] = {"id": identifier, "label": f"Synthetic {identifier}"}
        rows = sorted(by_id.values(), key=lambda row: row["id"])
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"{filename} now contains {len(rows)} records")


if __name__ == "__main__":
    main()
