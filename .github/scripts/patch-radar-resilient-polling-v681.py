#!/usr/bin/env python3
from pathlib import Path
import sys

MARKER = "WFGG_RADAR_RESILIENT_POLLING_V681"
DEFAULT_TARGET = Path("radar-ui-live/live-radar.html")

old = """async function runCollectorSearch(q){const started=await api('/api/radar/search/start',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({q})});let job=started.job;if(!job?.id)throw new Error('COLLECTOR_JOB_START_INVALID');for(;;){renderJob(job);if(job.status==='SUCCESS')return {job,player:job.player||null};if(job.status==='FAILED')throw new Error(job.error||'COLLECTOR_SEARCH_FAILED');await sleep(2000);const d=await api('/api/radar/search/status?id='+encodeURIComponent(job.id));job=d.job;if(!job)throw new Error('COLLECTOR_JOB_STATUS_INVALID')}}"""

new = r"""/* WFGG_RADAR_RESILIENT_POLLING_V681 */
const WFGG_RADAR_ACTIVE_JOB_KEY='wfgg_radar_active_job_v681';
const WFGG_RADAR_POLL_RETRY_MS=[1500,2500,4000,6000,8000,10000,12000,15000];
function rememberCollectorJob(job,q){try{if(job?.id)sessionStorage.setItem(WFGG_RADAR_ACTIVE_JOB_KEY,JSON.stringify({id:String(job.id),query:String(q||''),at:Date.now()}))}catch(_){}}
function forgetCollectorJob(){try{sessionStorage.removeItem(WFGG_RADAR_ACTIVE_JOB_KEY)}catch(_){}}
function savedCollectorJob(q){try{const raw=sessionStorage.getItem(WFGG_RADAR_ACTIVE_JOB_KEY);if(!raw)return null;const v=JSON.parse(raw);if(!v?.id||v.query!==String(q||'')||Date.now()-Number(v.at||0)>13*60*1000){forgetCollectorJob();return null}return v}catch(_){forgetCollectorJob();return null}}
function retryableCollectorPollError(err){const s=Number(err?.status||0);return !s||s===429||s>=500}
async function fetchCollectorJobResilient(id,lastJob){let failures=0;for(;;){try{const d=await api('/api/radar/search/status?id='+encodeURIComponent(id));if(!d.job)throw new Error('COLLECTOR_JOB_STATUS_INVALID');if(failures)setStatus('CONNEXION RÉTABLIE','Reprise du suivi du cycle…','ok');return d.job}catch(err){if(!retryableCollectorPollError(err))throw err;failures++;if(failures>WFGG_RADAR_POLL_RETRY_MS.length){const e=new Error('SUIVI RÉSEAU INDISPONIBLE · le cycle continue, relance RECHERCHER pour reprendre');e.code='COLLECTOR_POLL_NETWORK_UNAVAILABLE';e.cause=err;throw e}renderJob(lastJob);const delay=WFGG_RADAR_POLL_RETRY_MS[failures-1];setStatus('CONNEXION MOMENTANÉMENT PERDUE',`Cycle conservé · reprise ${failures}/${WFGG_RADAR_POLL_RETRY_MS.length} dans ${Math.ceil(delay/1000)} s`);await sleep(delay)}}}
async function loadOrStartCollectorJob(q){const saved=savedCollectorJob(q);if(saved){try{const d=await api('/api/radar/search/status?id='+encodeURIComponent(saved.id));if(d.job)return d.job;forgetCollectorJob()}catch(err){if(err?.status===404){forgetCollectorJob()}else if(retryableCollectorPollError(err)){return await fetchCollectorJobResilient(saved.id,{id:saved.id,query:q,status:'RUNNING',phase:'WAITING_FOR_CYCLE',regions:9})}else throw err}}const started=await api('/api/radar/search/start',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({q})});const job=started.job;if(!job?.id)throw new Error('COLLECTOR_JOB_START_INVALID');rememberCollectorJob(job,q);return job}
async function runCollectorSearch(q){let job=await loadOrStartCollectorJob(q);rememberCollectorJob(job,q);for(;;){renderJob(job);if(job.status==='SUCCESS'){forgetCollectorJob();return {job,player:job.player||null}}if(job.status==='FAILED'){forgetCollectorJob();throw new Error(job.error||'COLLECTOR_SEARCH_FAILED')}await sleep(2000);job=await fetchCollectorJobResilient(job.id,job);rememberCollectorJob(job,q)}}"""

def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TARGET
    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        print("RADAR_V681_RESILIENT_POLLING=ALREADY_PRESENT")
        return 0
    if old not in text:
        raise SystemExit("RADAR_V681_PATCH_ANCHOR_NOT_FOUND")
    text = text.replace(old, new, 1)
    target.write_text(text, encoding="utf-8")
    print("RADAR_V681_RESILIENT_POLLING=PATCHED")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
