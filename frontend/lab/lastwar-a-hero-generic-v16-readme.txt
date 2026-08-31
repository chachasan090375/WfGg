V16 — A_Hero generic nomenclature pass

Purpose:
- Stop assuming the Formation-board model is named Audie.
- Search reusable local asset indexes for A_Hero* naming families.
- Prioritize exact A_Hero_01, non-Audie assets, Formation/PVP/UI/LOD hints.
- Group base/High/LOD/skin suffix variants by common root.

Run:
  bash scripts/lastwar-a-hero-generic-v16.sh

Viewer:
  http://127.0.0.1:8788/lab/lastwar-a-hero-generic-v16.html?v=16

Next decision:
- If exact/non-Audie hits exist, feed those bundle/pathID candidates into the raw TypeTree mesh exporter and visual viewer.
- If zero hits exist in the reusable index, build/refresh the global Unity asset index and rerun V16.
