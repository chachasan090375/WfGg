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
pth=(R/'systemd/chacha-dev-nas-incremental-image-vault.path').read_text()
assert 'PathExists=/opt/chacha-dev/runtime/nas-image-vault/dirty.json' in pth
assert p['trigger_policy']['periodic_snapshot_timer'] is False
assert p['trigger_policy']['application_build_alone_marks_dirty'] is False
assert '/share/CACHEDEV1_DATA/ChaCha-DEV-HUB' in (R/'config/nas-incremental-image-vault.v1.json').read_text()
assert '/share/CACHEDEV2_DATA/ChaCha-DEV-Image-Vault' in (R/'config/nas-incremental-image-vault.v1.json').read_text()
assert '--mode snapshot' in svc and '--dirty-marker' in svc
promo=(R/'bin/governed-platform-promotion.py').read_text()
assert 'mark_nas_image_vault_dirty' in promo and 'PLATFORM_PROMOTION_FINALIZED' in promo
assert 'NO_CHANGE' in s
print('CHACHA_DEV_NAS_INCREMENTAL_IMAGE_VAULT_EVENT_TRIGGER_TEST=PASS')
