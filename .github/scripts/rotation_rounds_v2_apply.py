from pathlib import Path

# Reuse the reviewed UI patch specification, but apply its Train edits to a new
# v15 asset. The captured production v14 file and its SHA sidecar stay immutable.
spec_path = Path('.github/scripts/rotation_rounds_v2_ui_patch.py')
spec = spec_path.read_text(encoding='utf-8')

old = "train_path = Path('frontend/train-native/app.v14.live.js')\ntrain = train_path.read_text(encoding='utf-8')"
new = "base_train_path = Path('frontend/train-native/app.v14.live.js')\ntrain_path = Path('frontend/train-native/app.v15.js')\ntrain = base_train_path.read_text(encoding='utf-8')"
if old not in spec:
    raise SystemExit('Unable to redirect Train patch to v15 asset')
spec = spec.replace(old, new, 1)

exec(compile(spec, str(spec_path), 'exec'), {'__name__': '__main__'})

# Route only the test branch to the new native v15 asset.
worker_path = Path('frontend/_worker.js')
worker = worker_path.read_text(encoding='utf-8')
old_asset = "assetUrl.pathname = '/train-native/app.v14.live.js';"
new_asset = "assetUrl.pathname = '/train-native/app.v15.js';"
if old_asset not in worker:
    raise SystemExit('Native Train shadow asset route not found')
worker = worker.replace(old_asset, new_asset, 1)
worker_path.write_text(worker, encoding='utf-8')

print('WFGG_ROTATION_ROUNDS_V2_APPLY=OK')
