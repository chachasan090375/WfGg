#!/usr/bin/env python3
import json, pathlib
R=pathlib.Path(__file__).resolve().parents[1]
p=json.loads((R/'config/nas-incremental-image-vault.v1.json').read_text())
assert p['source_root']=='/share/CACHEDEV1_DATA/ChaCha-DEV-HUB'
assert p['vault_root']=='/share/CACHEDEV2_DATA/ChaCha-DEV-Image-Vault'
assert p['snapshot']['strategy']=='RSYNC_HARDLINK_INCREMENTAL'
assert p['verification']['post_copy_rsync_dry_run_must_be_empty'] is True
assert p['core_capsule']['secrets_forbidden'] is True
assert p['retention']['automatic_prune_enabled'] is False
assert p['authority']['destructive_delete'] is False
s=(R/'bin/nas_incremental_image_vault.py').read_text()
for x in ['git','bundle','sqlite3','--link-dest','RESTORE_VERIFIED','secrets_included']:
    assert x in s,x
print('CHACHA_DEV_NAS_INCREMENTAL_IMAGE_VAULT_TEST=PASS')

svc=(R/'systemd/chacha-dev-nas-incremental-image-vault.service').read_text()
tmr=(R/'systemd/chacha-dev-nas-incremental-image-vault.timer').read_text()
assert 'OnUnitActiveSec=30min' in tmr
assert '/share/CACHEDEV1_DATA/ChaCha-DEV-HUB' in (R/'config/nas-incremental-image-vault.v1.json').read_text()
assert '/share/CACHEDEV2_DATA/ChaCha-DEV-Image-Vault' in (R/'config/nas-incremental-image-vault.v1.json').read_text()
assert '--mode snapshot' in svc
print('CHACHA_DEV_NAS_INCREMENTAL_IMAGE_VAULT_TIMER_TEST=PASS')
