# WfGg Last War LAB — Global Graphics V32 — VALIDATED

Date: 2026-09-01
Branch: `lab-global-graphics-catalog-v32`
Validation workflow: `Last War Global Graphics V32 full smoke`
Successful run: `33495716400`

## Global catalog

- Assets indexed: **107,247**
- Physical hierarchy nodes: **121,761**
- Reconstruction graph nodes: **214,146**
- Reconstruction graph edges: **1,277,533**

## Advanced filter — Graphique ?

The V32 catalog classifies every indexed row with an independent `graphic_class` facet:

- **Graphique:** 56,599
- **Composant graphique:** 38,380
- **Non graphique:** 9,259
- **Indéterminé:** 3,009

Viewer labels:

- `Tous`
- `Oui — graphique`
- `Composant graphique`
- `Non — non graphique`
- `Indéterminé`

`Indéterminé` is deliberately preserved when evidence is insufficient; it is not forced to yes or no.

## Event registry / exact graph crosswalk

- Canonical registry entries loaded at runtime: **189**
- Direct event-token links before graph traversal: **1,471**
- Directly linked assets before graph traversal: **1,421**
- Exact graph seed nodes: **2,309**
- Exact graph-related nodes resolved: **22,165 / 22,165**
- Final event ↔ asset relations: **95,598**
- Unique assets linked to at least one event: **20,464**

Policy:

- `belongs-to` only comes from a direct curated event token on the resource/node itself.
- Exact graph neighbours/dependencies are classified as `used-by`, not event-owned.
- Candidate graph edges never propagate.
- `belongs-to` outranks `used-by` for the same event/asset pair.
- Graph traversal is deliberately bounded to two exact passes.

## Viewer V32

Local page:

`http://127.0.0.1:8788/lab/lastwar-global-graphics-viewer-v32.html`

Advanced filters include the previous family/form/context/scope/technical/confidence axes plus:

- `Graphique ?`
- `Événement`
- `Lien événement` (`Appartient à` / `Utilisé par`)

The documented PNG capture also records graphic classification and event relationships.

## Termux start

```bash
cd ~/wfgg-lastwar-preview
git fetch origin
git switch lab-global-graphics-catalog-v32 2>/dev/null || git switch -c lab-global-graphics-catalog-v32 --track origin/lab-global-graphics-catalog-v32
git pull --ff-only
bash scripts/lastwar-global-graphics-v32.sh
```

The first V32 build scans the exact reconstruction graph before starting the local viewer. Subsequent browsing uses the local indexed SQLite catalog and on-demand bundle rendering.
