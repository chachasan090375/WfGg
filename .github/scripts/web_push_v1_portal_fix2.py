from pathlib import Path
p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
if 'WFGG_WEB_PUSH_SW_RESET_GUARD_V2' not in s:
    old="""    if('serviceWorker' in navigator){
      const hadTrainController=!!navigator.serviceWorker.controller;

      Promise.all(["""
    new="""    if('serviceWorker' in navigator){
      const hadTrainController=!!navigator.serviceWorker.controller;
      /* WFGG_WEB_PUSH_SW_RESET_GUARD_V2 */
      let removedLegacyTrainWorker=false;

      Promise.all(["""
    if old not in s: raise SystemExit('SW reset start anchor missing')
    s=s.replace(old,new,1)
    old2='.map(registration=>registration.unregister())'
    new2=".map(async registration=>{const removed=await registration.unregister();if(removed)removedLegacyTrainWorker=true;return removed;})"
    if old2 not in s: raise SystemExit('unregister map anchor missing')
    s=s.replace(old2,new2,1)
    old3="""        if(
          hadTrainController &&
          sessionStorage.getItem(WFGG_SW_RESET_KEY)!=='1'
        ){"""
    new3="""        if(
          removedLegacyTrainWorker &&
          hadTrainController &&
          sessionStorage.getItem(WFGG_SW_RESET_KEY)!=='1'
        ){"""
    if old3 not in s: raise SystemExit('reload guard anchor missing')
    s=s.replace(old3,new3,1)
p.write_text(s,encoding='utf-8')
print('Push SW reset guard v2 applied')
