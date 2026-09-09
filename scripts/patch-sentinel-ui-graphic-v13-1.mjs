import fs from 'node:fs';
import crypto from 'node:crypto';

const appPath='frontend/train-native/app.v15.js';
const sentinelPath='frontend/train-native/sentinel-train-v1.js';
const checksumPath='frontend/train-native/app.v15.js.sha256';
let app=fs.readFileSync(appPath,'utf8');
let sentinel=fs.readFileSync(sentinelPath,'utf8');

function replaceOne(text,re,replacement,label){
  const matches=[...text.matchAll(new RegExp(re.source,re.flags.includes('g')?re.flags:re.flags+'g'))];
  if(matches.length!==1) throw new Error(`${label}: expected 1 match, got ${matches.length}`);
  return text.replace(re,replacement);
}
function replaceLiteral(text,from,to,label){
  const count=text.split(from).length-1;
  if(count!==1) throw new Error(`${label}: expected 1 occurrence, got ${count}`);
  return text.replace(from,to);
}

const geometryBlock=`    /* WFGG_SENTINEL_UI_GRAPHIC_V13_1
       Sur mobile, un contrôle hors du viewport n'est pas défectueux : Sentinel le
       centre d'abord, attend les états asynchrones, puis mesure l'intersection réelle.
       Aucun point hors écran n'est rabattu artificiellement sur le bord du viewport. */
    async function sentinelUiTick(){await Promise.resolve();await new Promise(r=>requestAnimationFrame(()=>r()));}
    async function sentinelUiGeometry(el,id,options={}){
        const waitMs=Math.max(0,Number(options.waitMs||0));
        const conditional=Boolean(options.conditional);
        const started=performance.now();
        const missing=()=>({id,ok:conditional,severity:conditional?'info':'error',reason:'missing',visible:false,inViewport:false,exposed:false,pointer:false,target:false,width:0,height:0,waitedMs:Math.round(performance.now()-started)});
        if(!el)return missing();
        const sample=()=>{
            const rect=el.getBoundingClientRect();
            const style=getComputedStyle(el);
            const visible=rect.width>0&&rect.height>0&&style.display!=='none'&&style.visibility!=='hidden'&&Number(style.opacity||1)>0.05;
            const left=Math.max(0,rect.left),right=Math.min(innerWidth,rect.right),topY=Math.max(0,rect.top),bottom=Math.min(innerHeight,rect.bottom);
            const inViewport=visible&&right>left&&bottom>topY;
            let exposed=false,top=null;
            if(inViewport&&document.elementsFromPoint){
                const x=(left+right)/2,y=(topY+bottom)/2;
                const stack=document.elementsFromPoint(x,y).filter(node=>!node.closest?.('#wfggTrainSentinelOverlay'));
                top=stack[0]||null;
                exposed=!top||top===el||el.contains(top);
            }else if(inViewport){exposed=true;}
            const pointer=style.pointerEvents!=='none';
            const target=rect.width>=32&&rect.height>=32;
            return {id,visible,inViewport,exposed,pointer,target,width:Math.round(rect.width),height:Math.round(rect.height),top:top?.id||top?.className||top?.tagName||''};
        };
        let g=sample();
        while(!g.visible&&performance.now()-started<waitMs){
            await new Promise(r=>setTimeout(r,120));
            await sentinelUiTick();
            g=sample();
        }
        if(g.visible){
            const bodyOverflow=document.body.style.overflow;
            try{
                document.body.style.overflow='';
                try{el.scrollIntoView({block:'center',inline:'nearest',behavior:'instant'});}catch(_){el.scrollIntoView({block:'center',inline:'nearest'});}
                await sentinelUiTick();
                await new Promise(r=>setTimeout(r,40));
            }finally{document.body.style.overflow=bodyOverflow;}
            g=sample();
        }
        const hardOk=g.visible&&g.inViewport&&g.exposed&&g.pointer&&g.target;
        const severity=hardOk?'ok':(!g.visible&&conditional?'info':'error');
        return {...g,ok:hardOk||severity==='info',severity,conditional,waitedMs:Math.round(performance.now()-started)};
    }
`;
app=replaceOne(app,/    function sentinelUiGeometry\(el,id\)\{[\s\S]*?    async function sentinelUiTick\(\)\{await Promise\.resolve\(\);await new Promise\(r=>requestAnimationFrame\(\(\)=>r\(\)\)\);\}\n/,geometryBlock,'geometry helper');

const replacements=[
 ["graphics.push(sentinelUiGeometry(profileBtn,'profile-edit-button'));","graphics.push(await sentinelUiGeometry(profileBtn,'profile-edit-button'));",'profile button'],
 ["graphics.push(sentinelUiGeometry(document.querySelector('#modal .btn.gold'),'profile-save-button'));","graphics.push(await sentinelUiGeometry(document.querySelector('#modal .btn.gold'),'profile-save-button'));",'profile save'],
 ["graphics.push(sentinelUiGeometry(alertsBtn,'alerts-home-button'));","graphics.push(await sentinelUiGeometry(alertsBtn,'alerts-home-button'));",'alerts home'],
 ["graphics.push(sentinelUiGeometry(serverPushBtn,'server-push-test-button'));","graphics.push(await sentinelUiGeometry(serverPushBtn,'server-push-test-button',{waitMs:3000,conditional:true}));",'server push'],
 ["graphics.push(sentinelUiGeometry(localPushBtn,'local-notification-test-button'));","graphics.push(await sentinelUiGeometry(localPushBtn,'local-notification-test-button',{waitMs:3000,conditional:true}));",'local push'],
 ["graphics.push(sentinelUiGeometry(modify,'notification-settings-modify'));","graphics.push(await sentinelUiGeometry(modify,'notification-settings-modify'));",'settings modify'],
 ["graphics.push(sentinelUiGeometry(unavailableBtn,'unavailability-home-button'));","graphics.push(await sentinelUiGeometry(unavailableBtn,'unavailability-home-button'));",'unavailability home'],
 ["graphics.push(sentinelUiGeometry(addUnavailability,'unavailability-add-button'));","graphics.push(await sentinelUiGeometry(addUnavailability,'unavailability-add-button'));",'unavailability add'],
 ["graphics.push(sentinelUiGeometry(rotationBtn,'rotation-home-button'));","graphics.push(await sentinelUiGeometry(rotationBtn,'rotation-home-button'));",'rotation home']
];
for(const [from,to,label] of replacements) app=replaceLiteral(app,from,to,label);

app=replaceLiteral(app,
"        const simFailed=simulations.filter(x=>!x.ok);\n        const graphicFailed=graphics.filter(x=>!x.ok);\n        return {readonly:true,simulations,graphics,simFailed,graphicFailed,notificationSettings:notificationSettingsIntentPlan()};",
"        const simFailed=simulations.filter(x=>!x.ok);\n        const graphicFailed=graphics.filter(x=>x.severity==='error'||!x.ok);\n        const graphicInfo=graphics.filter(x=>x.severity==='info');\n        return {readonly:true,simulations,graphics,simFailed,graphicFailed,graphicInfo,notificationSettings:notificationSettingsIntentPlan()};",
'probe result');

sentinel=replaceOne(sentinel,/    const graphicTotal=uiProbe\?\.graphics\?\.length\|\|0,graphicFailed=uiProbe\?\.graphicFailed\|\|\[\];\n    items\.push\(localCheck\([\s\S]*?\n    \)\);\n    const settingsPlan=/,`    const graphicTotal=uiProbe?.graphics?.length||0,graphicFailed=uiProbe?.graphicFailed||[],graphicInfo=uiProbe?.graphicInfo||[];
    const graphicOk=Math.max(0,graphicTotal-graphicFailed.length-graphicInfo.length);
    const graphicLevel=graphicFailed.length?'error':(graphicInfo.length?'info':'ok');
    const graphicDetail=[];
    if(graphicFailed.length)graphicDetail.push(graphicFailed.map(x=>\`${'${'}x.id}: visible=${'${'}x.visible} viewport=${'${'}x.inViewport} exposé=${'${'}x.exposed} pointer=${'${'}x.pointer} cible=${'${'}x.target} ${'${'}x.width||0}x${'${'}x.height||0}\`).join(' · '));
    if(graphicInfo.length)graphicDetail.push('Conditionnel : '+graphicInfo.map(x=>\`${'${'}x.id} masqué après ${'${'}x.waitedMs||0} ms\`).join(' · '));
    items.push(localCheck(
      'train-ui-graphic-audit',graphicLevel,'Analyse graphique des contrôles',
      'Contrôles critiques centrés puis visibles, cliquables, non recouverts et cible tactile suffisante',uiProbe?\`${'${'}graphicOk}/${'${'}graphicTotal} conformes${'${'}graphicInfo.length?\` · ${'${'}graphicInfo.length} conditionnel(s)\`:''}\`:'probe absent',
      graphicDetail.length?graphicDetail.join(' · '):'Chaque contrôle est centré par scrollIntoView avant mesure; les états Push asynchrones sont attendus jusqu’à 3 s.',
      graphicFailed.length?'Un contrôle reste réellement inaccessible après centrage et attente; ce n’est plus un simple élément sous la ligne de flottaison.':''
    ));
    const settingsPlan=`,'sentinel graphic check');

fs.writeFileSync(appPath,app);
fs.writeFileSync(sentinelPath,sentinel);
const digest=crypto.createHash('sha256').update(app).digest('hex');
fs.writeFileSync(checksumPath,`${digest}  app.v15.js\n`);
console.log('Sentinel UI graphic V13.1 patch applied');
