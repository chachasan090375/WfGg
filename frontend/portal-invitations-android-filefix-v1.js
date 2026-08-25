(() => {
'use strict';
/* WFGG_PORTAL_INVITATIONS_ANDROID_FILEFIX_V1
   Android DocumentsUI can expose .csv files as application/vnd.ms-excel or
   another provider-specific MIME type. The invitation module validates the
   CSV contents after selection, so the picker itself must not block the file.
   We also clear the input before every picker opening so selecting the same
   file again after a cancelled attempt always triggers a fresh selection.

   WFGG_PORTAL_INVITATIONS_ELO_CANONICAL_V1
   Invitation display canonicalises the historical aliases εlα ツ / εlo ツ
   to εlο ツ (Greek epsilon + Latin l + Greek omicron). This changes display
   text only; it never alters the imported file, authentication data or codes.
*/

const CANONICAL_ELO='εlο ツ';
function canonicaliseElo(value){
  return String(value??'').replaceAll('εlα ツ',CANONICAL_ELO).replaceAll('εlo ツ',CANONICAL_ELO);
}
function canonicaliseInvitationOutput(){
  const message=document.getElementById('inviteMessage');
  if(message&&typeof message.value==='string'){
    const fixed=canonicaliseElo(message.value);
    if(fixed!==message.value)message.value=fixed;
  }
  const root=document.getElementById('settingsContent');
  if(root){
    const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);
    let node;
    while((node=walker.nextNode())){
      const fixed=canonicaliseElo(node.nodeValue);
      if(fixed!==node.nodeValue)node.nodeValue=fixed;
    }
  }
}

function prepareCsvInput(input){
  if(!input)return;
  input.removeAttribute('accept');
  input.dataset.androidFilefix='v1';
}

function resetBeforePicker(event){
  const label=event.target?.closest?.('.invite-file-button');
  if(!label)return;
  const input=label.querySelector('#inviteCsvInput');
  if(!input)return;
  prepareCsvInput(input);
  try{input.value='';}catch{}
}

function sync(){
  document.querySelectorAll('#inviteCsvInput').forEach(prepareCsvInput);
  canonicaliseInvitationOutput();
}

sync();
new MutationObserver(sync).observe(document.documentElement,{childList:true,subtree:true});
document.addEventListener('pointerdown',resetBeforePicker,true);
document.addEventListener('click',event=>{
  canonicaliseInvitationOutput();
  resetBeforePicker(event);
  queueMicrotask(canonicaliseInvitationOutput);
},true);
document.addEventListener('change',event=>{
  if(event.target?.id==='inviteCsvInput')setTimeout(canonicaliseInvitationOutput,0);
},true);
})();
