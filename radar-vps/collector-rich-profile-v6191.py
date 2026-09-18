#!/usr/bin/env python3
from pathlib import Path
import argparse
import py_compile
import sqlite3


MARKER = "# WFGG_COLLECTOR_RICH_PROFILE_V6191"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 match, got {count}")
    return text.replace(old, new, 1)


def patch_agent(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if MARKER in text:
        py_compile.compile(str(path), doraise=True)
        print("COLLECTOR_V6191_CODE=ALREADY_PRESENT")
        return

    old_schema = """        inc.ensure_schema(c)\n"""
    new_schema = """        inc.ensure_schema(c)\n        # WFGG_COLLECTOR_RICH_PROFILE_V6191\n        # Rich profile values live in observations so the existing time-watermark\n        # backup policy captures them without adding a twelfth Collector table.\n        inc.ensure_column(c,'observations','army_power','INTEGER')\n        inc.ensure_column(c,'observations','army_kill','INTEGER')\n        inc.ensure_column(c,'observations','svip_level','INTEGER')\n        inc.ensure_column(c,'observations','country','TEXT')\n        inc.ensure_column(c,'observations','avatar_ref','TEXT')\n"""
    text = replace_once(text, old_schema, new_schema, "schema")

    old_norm = """      'power':p.get('power'),\n      'observed_at':str(p.get('observedAt') or p.get('observed_at') or now_iso())\n"""
    new_norm = """      'power':p.get('power'),\n      'army_power':p.get('armyPower') if 'armyPower' in p else p.get('army_power'),\n      'army_kill':p.get('armyKill') if 'armyKill' in p else p.get('army_kill'),\n      'svip_level':p.get('svipLevel') if 'svipLevel' in p else p.get('svip_level'),\n      'country':str(p.get('country') or '').strip(),\n      'avatar_ref':str(p.get('avatarRef') or p.get('avatar_ref') or '').strip(),\n      'observed_at':str(p.get('observedAt') or p.get('observed_at') or now_iso())\n"""
    text = replace_once(text, old_norm, new_norm, "normalization")

    old_ingest = """            did_change,is_new,effective=inc.upsert(c,p,cycle_id)\n            if did_change:\n                c.execute('''INSERT INTO observations(game_uid,observed_at,pseudo,server_id,alliance_id,\n                  alliance_tag,x,y,hq_level,power) VALUES(?,?,?,?,?,?,?,?,?,?)''',(\n                  p['game_uid'],p['observed_at'],effective['pseudo'],effective['server_id'],effective['alliance_id'],\n                  effective['alliance_tag'],effective['x'],effective['y'],effective['hq_level'],effective['power']))\n"""
    new_ingest = """            did_change,is_new,effective=inc.upsert(c,p,cycle_id)\n            has_rich=any(p.get(k) not in (None,'') for k in ('army_power','army_kill','svip_level','country','avatar_ref'))\n            if did_change or has_rich:\n                c.execute('''INSERT INTO observations(game_uid,observed_at,pseudo,server_id,alliance_id,\n                  alliance_tag,x,y,hq_level,power,army_power,army_kill,svip_level,country,avatar_ref)\n                  VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(\n                  p['game_uid'],p['observed_at'],effective['pseudo'],effective['server_id'],effective['alliance_id'],\n                  effective['alliance_tag'],effective['x'],effective['y'],effective['hq_level'],effective['power'],\n                  p.get('army_power'),p.get('army_kill'),p.get('svip_level'),p.get('country') or None,p.get('avatar_ref') or None))\n"""
    text = replace_once(text, old_ingest, new_ingest, "ingest")

    old_find = """def find_player(q):\n    with DB_LOCK,db() as c:\n        r=c.execute('SELECT * FROM players WHERE game_uid=? OR pseudo=? COLLATE NOCASE ORDER BY last_seen DESC LIMIT 1',(q,q)).fetchone()\n    return dict(r) if r else None\n"""
    new_find = """def _attach_rich_profile(c,row):\n    if not row:\n        return None\n    out=dict(row)\n    rich=c.execute('''SELECT army_power,army_kill,svip_level,country,avatar_ref,observed_at\n      FROM observations WHERE game_uid=? AND (army_power IS NOT NULL OR army_kill IS NOT NULL OR\n      svip_level IS NOT NULL OR country IS NOT NULL OR avatar_ref IS NOT NULL)\n      ORDER BY observed_at DESC,id DESC LIMIT 1''',(out['game_uid'],)).fetchone()\n    if rich:\n        out.update(dict(rich))\n    return out\n\n\ndef find_player(q):\n    with DB_LOCK,db() as c:\n        r=c.execute('SELECT * FROM players WHERE game_uid=? OR pseudo=? COLLATE NOCASE ORDER BY last_seen DESC LIMIT 1',(q,q)).fetchone()\n        return _attach_rich_profile(c,r)\n"""
    text = replace_once(text, old_find, new_find, "find player")

    old_search = """    with DB_LOCK,db() as c:\n        rows=c.execute('''SELECT * FROM players WHERE pseudo LIKE ? COLLATE NOCASE OR game_uid LIKE ?\n          ORDER BY last_seen DESC LIMIT ?''',(f'%{q}%',f'%{q}%',limit)).fetchall()\n    return [dict(r) for r in rows]\n"""
    new_search = """    with DB_LOCK,db() as c:\n        rows=c.execute('''SELECT * FROM players WHERE pseudo LIKE ? COLLATE NOCASE OR game_uid LIKE ?\n          ORDER BY last_seen DESC LIMIT ?''',(f'%{q}%',f'%{q}%',limit)).fetchall()\n        return [_attach_rich_profile(c,r) for r in rows]\n"""
    text = replace_once(text, old_search, new_search, "search players")

    path.write_text(text, encoding="utf-8")
    py_compile.compile(str(path), doraise=True)
    print("COLLECTOR_V6191_CODE=PATCHED")


def migrate_db(db_path: Path) -> None:
    con = sqlite3.connect(str(db_path), timeout=30)
    try:
        cols = {r[1] for r in con.execute("PRAGMA table_info(observations)")}
        for name, ddl in (
            ("army_power", "INTEGER"),
            ("army_kill", "INTEGER"),
            ("svip_level", "INTEGER"),
            ("country", "TEXT"),
            ("avatar_ref", "TEXT"),
        ):
            if name not in cols:
                con.execute(f"ALTER TABLE observations ADD COLUMN {name} {ddl}")
        con.commit()
        cols2 = {r[1] for r in con.execute("PRAGMA table_info(observations)")}
        required = {"army_power","army_kill","svip_level","country","avatar_ref"}
        if not required.issubset(cols2):
            raise SystemExit("COLLECTOR_V6191_SCHEMA_INCOMPLETE")
        print("COLLECTOR_V6191_SCHEMA=PASS")
        print("COLLECTOR_V6191_TABLE_COUNT_DELTA=0")
    finally:
        con.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)
    ap.add_argument("--db", required=True)
    args = ap.parse_args()
    patch_agent(Path(args.agent))
    migrate_db(Path(args.db))
    print("COLLECTOR_RICH_PROFILE_V6191=READY")


if __name__ == "__main__":
    main()
