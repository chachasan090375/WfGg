import tempfile
import unittest
from pathlib import Path
import importlib.util
import sys

ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("ke",ROOT/"knowledge_engine.py")
ke=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=ke
spec.loader.exec_module(ke)

class KnowledgeEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=ke.KnowledgeDB(self.root/"knowledge.db")

    def tearDown(self):
        self.tmp.cleanup()

    def test_text_index_and_query(self):
        src=self.root/"src"; src.mkdir()
        (src/"Net_Mail.lua").write_text('cmd = "mail.send"\nlocal field = "targetUid"\nlocal icon="ui/mail/icon.png"')
        result=ke.scan_source(self.db,"test","SOURCE_TREE",src,"1.0")
        self.assertEqual(result["status"],"SUCCESS")
        hits=self.db.search("mail.send")
        self.assertTrue(any(x["canonical_name"]=="mail.send" for x in hits))

    def test_lwlf_indexes_modules_and_fields(self):
        def s7(n):
            out=bytearray()
            while n >= 0x80:
                out.append((n & 0x7f)|0x80); n >>= 7
            out.append(n); return bytes(out)
        name=b"UI/LWSeason1/UILWSeasonServerDetail/View/View.luac"
        chunk=b"xxxx totalNum yyyy totalScore mail.send zzzz"
        pack=b"LWLF"+(1).to_bytes(4,"little")+(1).to_bytes(4,"little")+(1).to_bytes(4,"little")
        pack+=s7(len(name))+name+len(chunk).to_bytes(4,"little")+chunk
        src=self.root/"src"; src.mkdir(); (src/"LWScripts.data").write_bytes(pack)
        result=ke.scan_source(self.db,"lw","LASTWAR_STATIC",src,"1.0.351")
        self.assertEqual(result["status"],"SUCCESS")
        self.assertTrue(self.db.search("totalNum"))
        self.assertTrue(self.db.search("mail.send"))

    def test_unknown_binary_creates_decoder_task(self):
        src=self.root/"src"; src.mkdir(); (src/"mystery.bin").write_bytes(b"\x00\x01\x02\x03")
        ke.scan_source(self.db,"bin","ASSET_TREE",src,"v1")
        stats=self.db.stats()
        self.assertGreaterEqual(stats["unknownArtifacts"],1)
        self.assertGreaterEqual(stats["pendingTasks"],1)

    def test_png_dimensions(self):
        src=self.root/"src"; src.mkdir()
        png=b"\x89PNG\r\n\x1a\n"+b"\x00"*8+(64).to_bytes(4,"big")+(32).to_bytes(4,"big")+b"\x00"*32
        (src/"icon.png").write_bytes(png)
        ke.scan_source(self.db,"assets","ASSET_TREE",src,"v1")
        hits=self.db.search("icon.png")
        self.assertTrue(hits)
        detail=self.db.entity_detail(hits[0]["id"])
        self.assertTrue(any(a["predicate"]=="dimensions" and a["object_value"]=="64x32" for a in detail["assertions"]))

    def test_incremental_scan_skips_unchanged(self):
        src=self.root/"src"; src.mkdir(); p=src/"a.json"; p.write_text('{"serverId":8120}')
        first=ke.scan_source(self.db,"test","SOURCE_TREE",src,"v1")
        second=ke.scan_source(self.db,"test","SOURCE_TREE",src,"v1")
        self.assertEqual(first["changed"],1)
        self.assertEqual(second["changed"],0)

    def test_decoder_backlog_is_consumed_and_gap_remains_visible(self):
        src=self.root/"src"; src.mkdir()
        (src/"mystery.bin").write_bytes(b"\x00\x01\x02\x03")
        ke.scan_source(self.db,"bin","ASSET_TREE",src,"v1")
        before=self.db.stats()
        self.assertEqual(before["pendingTasks"],1)
        result=ke.process_tasks(self.db,10)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["state"],"WAITING_DECODER")
        after=self.db.stats()
        self.assertEqual(after["pendingTasks"],0)
        self.assertGreaterEqual(after["waitingTasks"],1)
        gaps=self.db.knowledge_gaps()
        self.assertTrue(any(x["state"]=="WAITING_DECODER" for x in gaps["tasks"]))

    def test_coverage_by_layer_reports_unknowns(self):
        src=self.root/"src"; src.mkdir()
        (src/"known.json").write_text('{"serverId":8120}')
        (src/"unknown.bin").write_bytes(b"\x00\x01")
        ke.scan_source(self.db,"mix","SOURCE_TREE",src,"v1")
        stats=self.db.stats()
        self.assertIn("DATA",stats["coverageByLayer"])
        layer=stats["coverageByLayer"]["DATA"]
        self.assertGreaterEqual(layer["artifacts"],1)
        self.assertGreaterEqual(layer["unknown"],1)
        self.assertLess(layer["coverage"],1.0)

    def test_database_survives_reopen(self):
        src=self.root/"src"; src.mkdir()
        (src/"a.json").write_text('{"serverId":8120,"totalNum":42}')
        ke.scan_source(self.db,"persist","SOURCE_TREE",src,"v1")
        self.db.db.close()
        db2=ke.KnowledgeDB(self.root/"knowledge.db")
        self.assertTrue(db2.search("serverId"))
        self.assertGreaterEqual(db2.stats()["artifacts"],1)
        db2.db.close()

if __name__=="__main__":
    unittest.main()
