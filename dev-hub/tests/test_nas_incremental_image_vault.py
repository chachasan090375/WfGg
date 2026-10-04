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

# F11 clean-host reconstructibility is a permanent invariant.
gsrc=p['core_capsule']['git_reconstruction_source']
assert gsrc['mode']=='DEDICATED_COMPLETE_BARE_REPOSITORY'
assert gsrc['require_non_shallow'] is True
assert gsrc['bundle_clean_clone_probe_required'] is True
assert gsrc['network_refresh_only_when_snapshot_required'] is True
assert p['verification']['clean_host_reconstruction_rehearsal_required'] is True
assert p['verification']['bundle_must_clone_on_empty_host'] is True
assert 'validate_bundle_clean_clone' in s and 'GIT_RECONSTRUCTION_SOURCE_NOT_COMPLETE' in s
clean=json.loads((R/'evidence/f11-resilience-clean-host-validation-2026-10-04.json').read_text())
assert clean['status']=='PASS'
assert clean['production_revision']=='7160ef74c760d5d4b4e3d0f81af1a8c1d6d06ecb'
assert clean['git_bundle']['clean_clone_verified'] is True
assert clean['clean_host_reconstruction']['git_clone_from_bundle']=='PASS'
assert clean['clean_host_reconstruction']['git_fsck']=='PASS'
assert clean['clean_host_reconstruction']['release_revision_verified'] is True
assert len(clean['clean_host_reconstruction']['sqlite_integrity'])==6
assert all(x['integrity_check']=='ok' for x in clean['clean_host_reconstruction']['sqlite_integrity'])
assert clean['clean_host_reconstruction']['systemd_started'] is False
assert clean['clean_host_reconstruction']['current_link_modified'] is False
print('CHACHA_DEV_F11_CLEAN_HOST_RECONSTRUCTIBILITY=PASS')
