#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import io
import json
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ADAPTER_PATH=ROOT/"dev-hub/adapters/storage-governor-adapter.py"
FIXTURE=ROOT/"dev-hub/fixtures/storage-governor.assess.v1.json"
CHAIN_PATH=ROOT/"dev-hub/adapters/storage-governor-incremental-chain.py"

spec=importlib.util.spec_from_file_location("storage_governor_adapter",ADAPTER_PATH)
mod=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)

chain_spec=importlib.util.spec_from_file_location("storage_governor_incremental_chain",CHAIN_PATH)
chain=importlib.util.module_from_spec(chain_spec)
assert chain_spec.loader is not None
chain_spec.loader.exec_module(chain)


class StorageGovernorContractTests(unittest.TestCase):
    def fixture(self):
        return json.loads(FIXTURE.read_text(encoding="utf-8"))

    def test_assess_contract_accepts_read(self):
        cfg,error=mod.validate_request(self.fixture())
        self.assertIsNone(error)
        self.assertEqual(cfg["action"],"assess")

    def test_master_requires_workspace_write(self):
        payload=self.fixture()
        payload["metadata"]["storage_governor"]["action"]="collector-master-snapshot"
        _,error=mod.validate_request(payload)
        self.assertEqual(error,"STORAGE_WRITE_ACTION_REQUIRES_WORKSPACE_WRITE")

    def test_unknown_action_blocked(self):
        payload=self.fixture()
        payload["metadata"]["storage_governor"]["action"]="delete-backups"
        _,error=mod.validate_request(payload)
        self.assertEqual(error,"STORAGE_GOVERNOR_ACTION_NOT_ALLOWED")

    def test_sqlite_metadata_readonly(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"collector.db"
            conn=sqlite3.connect(db)
            conn.execute("create table sample(id integer primary key, value text)")
            conn.execute("insert into sample(value) values ('ok')")
            conn.commit()
            conn.close()
            meta=mod.sqlite_metadata(db)
            self.assertGreaterEqual(meta["table_count"],1)
            self.assertGreater(meta["page_count"],0)
            conn=sqlite3.connect(f"file:{db}?mode=ro",uri=True)
            self.assertEqual(conn.execute("select count(*) from sample").fetchone()[0],1)
            conn.close()

    def test_incremental_discovery_is_schema_only(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"collector.db"
            conn=sqlite3.connect(db)
            conn.execute("create table cycles(id integer primary key, cycle_id integer not null, updated_at text)")
            conn.execute("create table players(id integer primary key, nickname text, cycle_id integer)")
            conn.execute("insert into cycles(cycle_id,updated_at) values (42,'2026-09-18T00:00:00Z')")
            conn.execute("insert into players(nickname,cycle_id) values ('SECRET_PLAYER',42)")
            conn.commit()
            conn.close()

            payload=self.fixture()
            payload["metadata"]["storage_governor"]["action"]="collector-incremental-discovery"
            old=os.environ.get("WFGG_COLLECTOR_DB")
            os.environ["WFGG_COLLECTOR_DB"]=str(db)
            try:
                out=io.StringIO()
                with redirect_stdout(out):
                    rc=mod.collector_incremental_discovery(payload)
                self.assertEqual(rc,0)
                value=json.loads(out.getvalue())
            finally:
                if old is None:
                    os.environ.pop("WFGG_COLLECTOR_DB",None)
                else:
                    os.environ["WFGG_COLLECTOR_DB"]=old

            self.assertEqual(value["status"],"OK")
            self.assertEqual(value["summary"],"COLLECTOR_INCREMENTAL_DISCOVERY_OK")
            details=value["evidence"][0]["details"]
            self.assertFalse(details["raw_row_data_exposed"])
            self.assertGreaterEqual(details["candidate_table_count"],1)
            serialized=json.dumps(value)
            self.assertNotIn("SECRET_PLAYER",serialized)
            self.assertIn("cycle_id",serialized)

    def test_incremental_plan_classifies_cycle_time_and_small_tables(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"collector.db"
            conn=sqlite3.connect(db)
            conn.execute("create table cycles(id integer primary key, started_at text, finished_at text)")
            conn.execute("create table players(id integer primary key, nickname text, last_change_cycle integer)")
            conn.execute("create table observations(id integer primary key, observed_at text, value text)")
            conn.execute("create table config(key text primary key, value text)")
            conn.execute("insert into cycles values (35,'2026-09-18T05:00:00Z','2026-09-18T05:18:00Z')")
            conn.execute("insert into players values (1,'SECRET',35)")
            conn.execute("insert into observations values (10,'2026-09-18T05:18:00Z','HIDDEN')")
            conn.execute("insert into config values ('a','b')")
            conn.commit()
            conn.close()

            payload=self.fixture()
            payload["metadata"]["storage_governor"]["action"]="collector-incremental-plan"
            old=os.environ.get("WFGG_COLLECTOR_DB")
            os.environ["WFGG_COLLECTOR_DB"]=str(db)
            try:
                out=io.StringIO()
                with redirect_stdout(out):
                    rc=mod.collector_incremental_plan(payload)
                self.assertEqual(rc,0)
                value=json.loads(out.getvalue())
            finally:
                if old is None:
                    os.environ.pop("WFGG_COLLECTOR_DB",None)
                else:
                    os.environ["WFGG_COLLECTOR_DB"]=old

            self.assertEqual(value["status"],"OK")
            details=value["evidence"][0]["details"]
            self.assertFalse(details["raw_row_data_exposed"])
            plans={x["table"]:x for x in details["plans"]}
            self.assertEqual(plans["cycles"]["mode"],"cycle-id")
            self.assertEqual(plans["players"]["mode"],"cycle-watermark")
            self.assertEqual(plans["observations"]["mode"],"time-watermark")
            self.assertEqual(plans["config"]["mode"],"full-table-small")
            serialized=json.dumps(value)
            self.assertNotIn("SECRET",serialized)
            self.assertNotIn("HIDDEN",serialized)

    def test_incremental_plan_explicit_dimension_refresh(self):
        with tempfile.TemporaryDirectory() as td:
            db=Path(td)/"collector.db"
            conn=sqlite3.connect(db)
            conn.execute("create table master_players(master_id integer, game_uid text, value text, primary key(master_id,game_uid))")
            conn.execute("create table player_aliases(game_uid text primary key, alias text)")
            conn.execute("create table player_identity(game_uid text primary key, identity text)")
            conn.executemany("insert into master_players values (?,?,?)", [(1,str(i),"x") for i in range(3)])
            conn.executemany("insert into player_aliases values (?,?)", [(str(i),"a") for i in range(3)])
            conn.executemany("insert into player_identity values (?,?)", [(str(i),"i") for i in range(3)])
            conn.commit()
            plans={}
            for table in ("master_players","player_aliases","player_identity"):
                meta=mod.table_schema(conn,table)
                plans[table]=mod.choose_incremental_policy(meta)
            conn.close()
            for table,plan in plans.items():
                self.assertEqual(plan["mode"],"full-table-dimension",table)
                self.assertEqual(plan["watermark_columns"],[],table)

    def test_incremental_anchor_and_package_contract_permissions(self):
        payload=self.fixture()
        payload["metadata"]["storage_governor"]["action"]="collector-incremental-anchor"
        _,error=mod.validate_request(payload)
        self.assertEqual(error,"STORAGE_WRITE_ACTION_REQUIRES_WORKSPACE_WRITE")
        payload["task"]["permission"]="workspace-write"
        cfg,error=mod.validate_request(payload)
        self.assertIsNone(error)
        self.assertEqual(cfg["action"],"collector-incremental-anchor")

        payload["metadata"]["storage_governor"]["action"]="collector-incremental-package"
        cfg,error=mod.validate_request(payload)
        self.assertIsNone(error)
        self.assertEqual(cfg["action"],"collector-incremental-package")

    def test_incremental_chain_generates_one_completed_cycle(self):
        conn=sqlite3.connect(":memory:")
        conn.executescript("""
        create table masters(id integer primary key, created_at text, name text);
        create table master_players(master_id integer, game_uid text, value text, primary key(master_id,game_uid));
        create table player_identity(game_uid text primary key, identity text);
        create table player_aliases(game_uid text, pseudo_key text, alias text, primary key(game_uid,pseudo_key));
        create table identity_coverage(scope_id text primary key, value text);
        create table cycles(id integer primary key, started_at text, finished_at text);
        create table players(game_uid text primary key, last_change_cycle integer, name text);
        create table cycle_baseline(cycle_id integer, game_uid text, value text, primary key(cycle_id,game_uid));
        create table cycle_seen(cycle_id integer, game_uid text, primary key(cycle_id,game_uid));
        create table cycle_changes(id integer primary key, cycle_id integer, game_uid text, changed_at text);
        create table observations(id integer primary key, observed_at text, value text);

        insert into masters values(1,'2026-09-11T22:23:30Z','m');
        insert into master_players values(1,'u1','v');
        insert into player_identity values('u1','i');
        insert into player_aliases values('u1','p','a');
        insert into identity_coverage values('s','ok');
        insert into cycles values(35,'2026-09-18T05:00:00Z','2026-09-18T05:18:00Z');
        insert into cycles values(36,'2026-09-18T06:00:00Z','2026-09-18T06:18:00Z');
        insert into players values('u1',36,'player');
        insert into cycle_baseline values(36,'u1','b');
        insert into cycle_seen values(36,'u1');
        insert into cycle_changes values(100,36,'u1','2026-09-18T06:10:00Z');
        insert into observations values(127000,'2026-09-18T06:10:00Z','obs');
        """)
        state=chain.make_anchor_state(
            master_archive="projects/wfgg/backups/collector-master.sql.gz",
            master_sha256="sha256:"+"a"*64,
            master_created_at="2026-09-18T08:57:57Z",
            baseline_cycle=35,
            observations_watermark={"observed_at":"2026-09-18T05:18:47Z","id":126611},
            masters_watermark={"created_at":"2026-09-11T22:23:30Z","id":1},
            plan_digest="sha256:"+"b"*64,
        )
        lines=[]
        package=chain.generate_incremental_sql(conn,state,lines.append)
        self.assertIsNotNone(package)
        self.assertEqual(package["sequence"],1)
        self.assertEqual(package["from_cycle"],35)
        self.assertEqual(package["to_cycle"],36)
        self.assertEqual(package["watermarks"]["cycle"],36)
        self.assertEqual(package["row_counts"]["cycles"],1)
        self.assertEqual(package["row_counts"]["cycle_baseline"],1)
        self.assertEqual(package["row_counts"]["players"],1)
        sql="\n".join(lines)
        self.assertIn('DELETE FROM "master_players";',sql)
        self.assertIn('DELETE FROM "player_aliases";',sql)
        self.assertIn('INSERT OR REPLACE INTO "cycle_baseline"',sql)
        self.assertIn("BEGIN TRANSACTION;",sql)
        self.assertIn("COMMIT;",sql)

    def test_incremental_chain_noop_without_new_completed_cycle(self):
        conn=sqlite3.connect(":memory:")
        conn.execute("create table cycles(id integer primary key, finished_at text)")
        conn.execute("insert into cycles values(35,'2026-09-18T05:18:00Z')")
        state=chain.make_anchor_state(
            master_archive="projects/wfgg/backups/collector-master.sql.gz",
            master_sha256="sha256:"+"a"*64,
            master_created_at="2026-09-18T08:57:57Z",
            baseline_cycle=35,
            observations_watermark={},
            masters_watermark={},
            plan_digest="sha256:"+"b"*64,
        )
        self.assertIsNone(chain.next_completed_cycle(conn,35))

    def test_source_safety_invariants(self):
        text=ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn('mode=ro',text)
        self.assertIn('conn.execute("BEGIN")',text)
        self.assertIn('collector_service_stopped":False',text)
        self.assertIn("COLLECTOR_MASTER_ALREADY_EXISTS",text)
        self.assertIn("COLLECTOR_INCREMENTAL_DISCOVERY_OK",text)
        self.assertIn("COLLECTOR_INCREMENTAL_PLAN_OK",text)
        self.assertIn("COLLECTOR_INCREMENTAL_CHAIN_ANCHORED",text)
        self.assertIn("COLLECTOR_INCREMENTAL_PACKAGE_CREATED",text)
        self.assertIn("COLLECTOR_INCREMENTAL_NOOP",text)
        self.assertIn('"raw_row_data_exposed":False',text)
        self.assertIn("shell=False",text)
        self.assertNotIn("systemctl stop",text)
        self.assertNotIn("rm -rf",text)


if __name__=="__main__":
    unittest.main()
