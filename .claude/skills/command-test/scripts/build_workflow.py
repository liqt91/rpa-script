# -*- coding: utf-8 -*-
"""Build a dedicated command-test workflow in data/data.db.

Reads a spec JSON (UTF-8) and inserts a workflow + nodes, optionally copying
elements from another workflow's element library. Designed for the
command-test skill: deterministic DB writes, no Chinese through shell stdin.

Usage (from repo root):
    python .claude/skills/command-test/scripts/build_workflow.py --spec spec.json
"""
import argparse
import datetime
import json
import os
import sqlite3
import sys
import uuid

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

GENERIC = {"onError": "stop", "retryCount": 3, "timeout": 10, "description": ""}


def _db_path(override: str | None) -> str:
    if override:
        return override
    path = os.path.join(os.getcwd(), "data", "data.db")
    if not os.path.isfile(path):
        sys.exit(f"data.db not found at {path} (run from repo root)")
    return path


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True, help="UTF-8 spec JSON path")
    ap.add_argument("--db", default=None, help="override data.db path")
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as f:
        spec = json.load(f)

    name = spec["name"]
    conn = sqlite3.connect(_db_path(args.db))
    c = conn.cursor()

    row = c.execute("select id from workflows where name=?", (name,)).fetchone()
    if row:
        sys.exit(f"workflow '{name}' already exists (id={row[0]}); choose another name")

    now = _now()
    c.execute(
        "insert into workflows (uuid,name,description,url,framework,target_browser,"
        "parameters,api_enabled,api_key,created_at,updated_at) values (?,?,?,?,?,?,?,?,?,?,?)",
        (uuid.uuid4().hex, name, spec.get("description", ""), "", "DrissionPage", "",
         "[]", 0, "", now, now),
    )
    wf_id = c.lastrowid
    print(f"workflow id = {wf_id} ({name})")

    el_cols = [r[1] for r in c.execute("pragma table_info(workflow_elements)").fetchall()]
    for item in spec.get("elementsToCopy", []):
        if "id" in item:
            src = c.execute("select * from workflow_elements where id=?", (item["id"],)).fetchone()
        else:
            src = c.execute(
                "select * from workflow_elements where workflow_id=? and name=?",
                (item["workflowId"], item["name"]),
            ).fetchone()
        if not src:
            sys.exit(f"element not found: {item}")
        d = dict(zip(el_cols, src))
        d["workflow_id"] = wf_id
        d["created_at"] = now
        d["updated_at"] = now
        ins = [k for k in d if k != "id"]
        c.execute(
            "insert into workflow_elements (%s) values (%s)" % (",".join(ins), ",".join("?" * len(ins))),
            [d[k] for k in ins],
        )
        print(f"copied element: {d['name']}")

    for el in spec.get("elements", []):
        c.execute(
            "insert into workflow_elements (workflow_id,name,element_kind,web_selector,"
            "element_type,created_at,updated_at) values (?,?,?,?,?,?,?)",
            (wf_id, el["name"], el.get("elementKind", "plain"), el["selector"],
             "web", now, now),
        )
        print(f"created element: {el['name']} -> {el['selector']}")

    id_by_order = {}
    pending_parent = []
    for node in spec["nodes"]:
        extra = dict(GENERIC)
        extra.update(node.get("extra") or {})
        c.execute(
            "insert into workflow_nodes (workflow_id,parent_id,[order],[type],action,"
            "element_name,extra,enabled,created_at) values (?,?,?,?,?,?,?,?,?)",
            (wf_id, None, node["order"], node["cmd"], None, node.get("elementName"),
             json.dumps(extra, ensure_ascii=False), 1, now),
        )
        node_id = c.lastrowid
        id_by_order[node["order"]] = node_id
        if "parentOrder" in node:
            pending_parent.append((node_id, node["parentOrder"]))

    for node_id, parent_order in pending_parent:
        if parent_order not in id_by_order:
            sys.exit(f"parentOrder {parent_order} not found among node orders "
                     f"{sorted(id_by_order)}")
        c.execute("update workflow_nodes set parent_id=? where id=?",
                  (id_by_order[parent_order], node_id))
    conn.commit()

    rows = c.execute(
        "select [order],[type],parent_id,element_name,extra from workflow_nodes "
        "where workflow_id=? order by [order]", (wf_id,),
    ).fetchall()
    parent_by_id = {nid: o for o, nid in id_by_order.items()}
    for r in rows:
        parent = f"<=order {parent_by_id[r[2]]}" if r[2] else ""
        print(f"  {r[0]:>2} {r[1]:<16} {parent:<12} {r[3] or ''} | {(r[4] or '')[:60]}")
    print(f"inserted {len(rows)} nodes ({len(pending_parent)} nested) — verify Chinese above is intact")
    conn.close()


if __name__ == "__main__":
    main()
