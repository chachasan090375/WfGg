import { DatabaseSync } from 'node:sqlite';

function plainRow(row){
  if(row == null) return null;
  const out={};
  for(const [k,v] of Object.entries(row)) out[k]=typeof v==='bigint'?Number(v):v;
  return out;
}

export class D1SqlitePrepared {
  constructor(stmt){ this.stmt=stmt; this.args=[]; }
  bind(...args){ this.args=args; return this; }
  async first(){ return plainRow(this.stmt.get(...this.args)); }
  async all(){ return { results:this.stmt.all(...this.args).map(plainRow), success:true, meta:{} }; }
  async run(){
    const r=this.stmt.run(...this.args);
    return { success:true, meta:{ changes:Number(r.changes||0), last_row_id:r.lastInsertRowid==null?null:Number(r.lastInsertRowid) } };
  }
}

export class D1SqliteBinding {
  constructor(path,{readonly=false}={}){
    this.path=path;
    this.db=new DatabaseSync(path,{readOnly:readonly});
    if(!readonly){
      this.db.exec('PRAGMA journal_mode=WAL;');
      this.db.exec('PRAGMA synchronous=FULL;');
      this.db.exec('PRAGMA foreign_keys=ON;');
      this.db.exec('PRAGMA busy_timeout=5000;');
    }
  }
  prepare(sql){ return new D1SqlitePrepared(this.db.prepare(sql)); }
  close(){ this.db.close(); }
}
