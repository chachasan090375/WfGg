(() => {
'use strict';
/* WFGG_PORTAL_INVITATIONS_ANDROID_FILEFIX_V1
   Android DocumentsUI can expose .csv files as application/vnd.ms-excel or
   another provider-specific MIME type. The invitation module validates the
   CSV contents after selection, so the picker itself must not block the file.
   We also clear the input before every picker opening so selecting the same
   file again after a cancelled attempt always triggers a fresh selection.
*/

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
}

sync();
new MutationObserver(sync).observe(document.documentElement,{childList:true,subtree:true});
document.addEventListener('pointerdown',resetBeforePicker,true);
document.addEventListener('click',resetBeforePicker,true);
})();
