#!/usr/bin/env node
import http from 'node:http';
import fs from 'node:fs';
import crypto from 'node:crypto';
import {D1SqliteBinding} from '../lib/d1-sqlite-binding.mjs';
const bind=process.env.CHACHA_D1_LOCAL_BIND||'127.0.0.1';
const port=Number(process.env.CHACHA_D1_LOCAL_PORT||'8871');
const dbPath=process.env.CHACHA_D1_LOCAL_DB;
const workerPath=process.env.CHACHA_D1_LOCAL_WORKER;
const service=process.env.CHACHA_D1_LOCAL_SERVICE||'chacha-d1-local-shadow';
if(!dbPath||!workerPath)throw new Error('CHACHA_D1_LOCAL_DB_AND_WORKER_REQUIRED');
const source=fs.readFileSync(workerPath,'utf8');const digest=crypto.createHash('sha256').update(source).digest('hex');
const expected=String(process.env.CHACHA_D1_LOCAL_WORKER_SHA256||'').replace(/^sha256:/,'');if(expected&&digest!==expected)throw new Error('WORKER_DIGEST_MISMATCH');
const worker=(await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))).default;if(!worker||typeof worker.fetch!=='function')throw new Error('WORKER_FETCH_MISSING');
const DB=new D1SqliteBinding(dbPath);
const env={DB};
for(const name of ['SENTINEL_URL','ASSURANCE_EXCHANGE_URL','GUARDIAN_URL','GITHUB_TOKEN'])if(process.env['CHACHA_'+name])env[name]=process.env['CHACHA_'+name];
function readBody(req){return new Promise((resolve,reject)=>{const p=[];let n=0;req.on('data',c=>{n+=c.length;if(n>2*1024*1024){reject(new Error('REQUEST_TOO_LARGE'));req.destroy();return;}p.push(c)});req.on('end',()=>resolve(Buffer.concat(p)));req.on('error',reject);});}
const server=http.createServer(async(req,res)=>{try{if(req.url==='/__sovereign/healthz'){res.writeHead(200,{'content-type':'application/json','cache-control':'no-store'});res.end(JSON.stringify({status:'ok',service,state_backend:'SQLITE_LOCAL',db_path:dbPath,worker_path:workerPath,worker_sha256:'sha256:'+digest,production_authority:false,automatic_external_spend_eur:0}));return;}const body=['GET','HEAD'].includes(req.method||'GET')?Buffer.alloc(0):await readBody(req);const headers=new Headers();for(const [k,v] of Object.entries(req.headers))if(v!==undefined)headers.set(k,Array.isArray(v)?v.join(', '):String(v));const init={method:req.method,headers};if(body.length)init.body=body;const request=new Request(`http://${bind}:${port}${req.url||'/'}`,init);const response=await worker.fetch(request,env);const out=Buffer.from(await response.arrayBuffer());const rh={};response.headers.forEach((v,k)=>rh[k]=v);res.writeHead(response.status,rh);res.end(out);}catch(err){res.writeHead(503,{'content-type':'application/json'});res.end(JSON.stringify({error:'d1_worker_local_runtime_exception',service,reason:String(err?.message||err),fail_closed:true}));}});
server.listen(port,bind,()=>console.log(JSON.stringify({schema:'chacha.dev/d1-worker-local-runtime/v1',status:'READY',service,bind,port,db_path:dbPath,worker_sha256:'sha256:'+digest,production_authority:false,automatic_external_spend_eur:0})));
for(const sig of ['SIGTERM','SIGINT'])process.on(sig,()=>server.close(()=>{DB.close();process.exit(0)}));
