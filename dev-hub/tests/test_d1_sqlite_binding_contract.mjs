#!/usr/bin/env node
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {D1SqliteBinding} from '../lib/d1-sqlite-binding.mjs';
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'chacha-d1-sqlite-'));const dbp=path.join(dir,'test.db');const DB=new D1SqliteBinding(dbp);
try{
 await DB.prepare('create table t(id text primary key,v text not null,updated_at text)').run();
 let r=await DB.prepare("insert into t(id,v,updated_at) values(?1,?2,datetime('now'))").bind('a','one').run(); if(r.meta.changes!==1)throw new Error('INSERT_CHANGES');
 r=await DB.prepare("insert or ignore into t(id,v,updated_at) values(?1,?2,datetime('now'))").bind('a','two').run(); if(r.meta.changes!==0)throw new Error('INSERT_IGNORE_CHANGES');
 r=await DB.prepare("insert into t(id,v,updated_at) values(?1,?2,datetime('now')) on conflict(id) do update set v=excluded.v,updated_at=datetime('now')").bind('a','three').run(); if(r.meta.changes!==1)throw new Error('UPSERT_CHANGES');
 const one=await DB.prepare('select id,v,updated_at from t where id=?1').bind('a').first();if(!one||one.v!=='three'||!one.updated_at)throw new Error('FIRST_SEMANTICS');
 const none=await DB.prepare('select id from t where id=?1').bind('missing').first();if(none!==null)throw new Error('FIRST_NULL_SEMANTICS');
 const all=await DB.prepare('select id,v from t order by id').all();if(all.success!==true||all.results.length!==1||all.results[0].id!=='a')throw new Error('ALL_SEMANTICS');
 r=await DB.prepare('update t set v=?2 where id=?1').bind('a','four').run();if(r.meta.changes!==1)throw new Error('UPDATE_CHANGES');
 r=await DB.prepare('delete from t where id=?1').bind('a').run();if(r.meta.changes!==1)throw new Error('DELETE_CHANGES');
 console.log('CHACHA_DEV_D1_SQLITE_BINDING_CONTRACT=PASS');
 console.log('D1_API_SURFACE=prepare.bind.first.all.run');
 console.log('AUTOMATIC_EXTERNAL_SPEND_EUR=0');
} finally {DB.close();fs.rmSync(dir,{recursive:true,force:true});}
