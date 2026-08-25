from pathlib import Path

index=Path('frontend/index.html')
s=index.read_text(encoding='utf-8')
needle='  <script src="portal-invitations-xlsx-v1.js?v=001"></script>\n'
insert=needle+'  <script src="portal-invitations-lastwar-safe-v1.js?v=001"></script>\n'
if 'portal-invitations-lastwar-safe-v1.js' not in s:
    if needle not in s: raise SystemExit('index invitations XLSX marker missing')
    s=s.replace(needle,insert,1)
index.write_text(s,encoding='utf-8')

qa=Path('.github/qa/portal-invitations-recette.mjs')
q=qa.read_text(encoding='utf-8')
start=q.index('  const r4=await page.locator(\'#inviteMessage\').inputValue();')
end=q.index('  const metrics=await page.evaluate',start)
new=r'''  await page.waitForFunction(()=>document.querySelector('#inviteMessage')?.dataset.lastwarSafe==='v1');
  const safe=await page.evaluate(()=>window.WFGG_LASTWAR_CHAT_SAFE_TEST);
  assert.equal(safe.MAX_CHARS,240);
  const r4blocks=await page.evaluate(()=>window.WFGG_LASTWAR_CHAT_SAFE_TEST.buildBlocks('Alpha R4','R4','111111'));
  assert.ok(r4blocks.length>=4);
  assert.ok(r4blocks.every(x=>x.length<=240),JSON.stringify(r4blocks.map(x=>x.length)));
  const r4=r4blocks.join('\n');
  assert.ok(r4.includes('Alpha R4'));
  assert.ok(r4.includes('wfgg.pages.dev'));
  assert.ok(!r4.includes('https://'),'Last War mode must avoid full URL scheme');
  assert.ok(r4.includes("investissement durant toute l'Inter-Saison"));
  assert.ok(r4.includes('111111'));
  for(const name of ['Metatouk','Ogie Ogilthorpe 7','ValFada','Shockwave XY','Sab93fr','εlο ツ','cat 49','Flawene']) assert.ok(r4.includes(name),`missing thanks ${name}`);
  assert.ok(!r4.includes('εlα ツ'),'old alpha alias leaked into invitation');
  assert.ok(!r4.includes('εlo ツ'),'Latin-o alias leaked into invitation');
  for(const name of ['El Tonton','Le Ced83','SnooPsy']) assert.ok(!r4.includes(name),`excluded thanks leaked ${name}`);
  assert.ok(r4.includes('Ton rang R4'));
  assert.ok(r4.includes('Joueurs & accès'));
  assert.ok(r4.includes('réinitialisation des codes'));
  const emoji=/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u;
  assert.ok(r4blocks.every(x=>!emoji.test(x)),'Unicode emoji leaked into Last War blocks');

  const first=await page.locator('#inviteMessage').inputValue();
  assert.ok(first.length<=240);
  assert.ok(first.includes('Alpha R4'));
  assert.equal(await page.locator('#inviteCopySent').isDisabled(),true,'mark-sent copy must wait for final block');
  const meta=await page.locator('[data-lastwar-safe-meta]').textContent();
  assert.match(meta,/Bloc 1\//);
  assert.match(meta,/sans emoji/);
  for(let i=1;i<r4blocks.length;i++)await page.locator('[data-lastwar-safe-next]').click();
  assert.equal(await page.locator('#inviteCopySent').isDisabled(),false,'final block must allow copy + mark sent');
  assert.match(await page.locator('#inviteMessage').inputValue(),/111111/);

  await page.locator('#inviteToggleSent').click();
  const storage1=await page.evaluate(()=>JSON.stringify({...localStorage}));
  assert.ok(!storage1.includes('111111'),'personal code persisted in localStorage');
  assert.ok(!storage1.includes('222222'),'personal code persisted in localStorage');
  assert.ok(!storage1.includes('333333'),'personal code persisted in localStorage');

  await page.locator('#inviteNext').click();
  await page.waitForFunction(()=>document.querySelector('#inviteMessage')?.dataset.lastwarSafe==='v1');
  const r3blocks=await page.evaluate(()=>window.WFGG_LASTWAR_CHAT_SAFE_TEST.buildBlocks('Bravo R3','R3','222222'));
  const r3=r3blocks.join('\n');
  assert.ok(r3blocks.every(x=>x.length<=240));
  assert.ok(r3.includes('Bravo R3'));
  assert.ok(r3.includes('222222'));
  assert.ok(!r3.includes('Ton rang R3'));
  assert.ok(!r3.includes('outils du bureau'));

  await page.locator('#inviteNext').click();
  await page.waitForFunction(()=>document.querySelector('#inviteMessage')?.dataset.lastwarSafe==='v1');
  const r5blocks=await page.evaluate(()=>window.WFGG_LASTWAR_CHAT_SAFE_TEST.buildBlocks('Charlie R5','R5','333333'));
  const r5=r5blocks.join('\n');
  assert.ok(r5blocks.every(x=>x.length<=240));
  assert.ok(r5.includes('Charlie R5'));
  assert.ok(r5.includes('333333'));
  assert.ok(r5.includes('Ton rang R5'));
  assert.ok(r5.includes('leadership R5'));

'''
q=q[:start]+new+q[end:]
qa.write_text(q,encoding='utf-8')
print('patched index and invitation QA for Last War safe mode')
