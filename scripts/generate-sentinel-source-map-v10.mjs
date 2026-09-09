import fs from 'node:fs';
import crypto from 'node:crypto';
import { execSync } from 'node:child_process';

function sha256(text){return crypto.createHash('sha256').update(text).digest('hex');}
function lineOf(text,needle){
  const idx=text.indexOf(needle);
  return idx<0?null:text.slice(0,idx).split('\n').length;
}
function meta(path,anchors){
  const text=fs.readFileSync(path,'utf8');
  const lines={};
  for(const [name,needle] of Object.entries(anchors))lines[name]=lineOf(text,needle);
  return {sha256:sha256(text),lineCount:text.split('\n').length,anchors:lines};
}

let commit=process.env.GITHUB_SHA||'';
if(!commit){
  try{commit=execSync('git rev-parse HEAD',{encoding:'utf8'}).trim();}catch{commit='unknown';}
}

const files={
  'frontend/_worker.js':meta('frontend/_worker.js',{
    proxyRoute:'async function proxyRoute(',
    sentinelEdgeFetchJson:'async function sentinelEdgeFetchJson(',
    sentinelPortalMeAtEdge:'async function sentinelPortalMeAtEdge(',
    sentinelRunDeepDiagnostics:'async function sentinelRunDeepDiagnostics(',
    runSentinelAtPortalEdge:'async function runSentinelAtPortalEdge(',
    routeTrain:'async function routeTrain('
  }),
  'frontend/train-native/sentinel-train-v1.js':meta('frontend/train-native/sentinel-train-v1.js',{
    localChecks:'async function localChecks(',
    runSentinel:'async function runSentinel(',
    renderReport:'function renderReport(',
    reportText:'function reportText('
  })
};

const map={
  version:'sentinel-portal-source-map-v10',
  repository:'chachasan090375/WfGg',
  sourceCommit:commit,
  generatedAt:new Date().toISOString(),
  files
};
fs.writeFileSync('frontend/sentinel-source-map-v10.json',JSON.stringify(map,null,2)+'\n');
console.log('WFGG_SENTINEL_PORTAL_SOURCE_MAP_V10=OK commit='+commit);
