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

spec=importlib.util.spec_from_file_location("storage_governor_adapter",ADAPTER_PATH)
mod=importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


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
        self.assertEqual(error,"COLLECTOR_MASTER_REQUIRES_WORKSPACE_WRITE")

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

    def test_source_safety_invariants(self):
        text=ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertIn('mode=ro',text)
        self.assertIn('conn.execute("BEGIN")',text)
        self.assertIn('collector_service_stopped":False',text)
        self.assertIn("COLLECTOR_MASTER_ALREADY_EXISTS",text)
        self.assertIn("COLLECTOR_INCREMENTAL_DISCOVERY_OK",text)
        self.assertIn('"raw_row_data_exposed":False',text)
        self.assertIn("shell=False",text)
        self.assertNotIn("systemctl stop",text)
        self.assertNotIn("rm -rf",text)


if __name__=="__main__":
    unittest.main()
