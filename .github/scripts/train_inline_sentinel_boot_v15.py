from pathlib import Path

app_path = Path('frontend/train-native/app.v15.js')
worker_path = Path('frontend/_worker.js')
app = app_path.read_text()
worker = worker_path.read_text()

marker = 'WFGG_TRAIN_INLINE_SENTINEL_BOOT_V15'
if marker not in app:
    anchor = "    let syncing = false;\n"
    assert anchor in app, 'syncing anchor missing'
    app = app.replace(anchor, anchor + "    let lastApiDiagnostic = null;\n    let lastSnapshotDiagnostic = null;\n    function recordApiDiagnostic(path, details = {}) {\n        lastApiDiagnostic = {\n            path: String(path || ''),\n            status: Number(details.status || 0),\n            error: String(details.error || ''),\n            route: String(details.route || ''),\n            bridge: String(details.bridge || ''),\n            ok: Boolean(details.ok),\n            at: new Date().toISOString()\n        };\n        return lastApiDiagnostic;\n    }\n", 1)

    network_old = "        catch (e) {\n            setSyncStatus('off');\n            throw new Error('Réseau indisponible');\n        }\n        let data = {};\n"
    network_new = "        catch (e) {\n            setSyncStatus('off');\n            recordApiDiagnostic(path, { status: 0, error: String((e && e.message) || e || 'Réseau indisponible') });\n            throw new Error('Réseau indisponible');\n        }\n        let data = {};\n"
    assert network_old in app, 'api network block missing'
    app = app.replace(network_old, network_new, 1)

    parse_old = "        catch (e) { }\n        if (res.status === 401) {\n"
    parse_new = "        catch (e) { }\n        const apiRoute = res.headers.get('X-WfGg-Route') || '';\n        const apiBridge = res.headers.get('X-WfGg-Portal-Bridge') || '';\n        if (res.status === 401) {\n"
    assert parse_old in app, 'api parse block missing'
    app = app.replace(parse_old, parse_new, 1)

    auth_old = "            throw new Error(data.error || 'Session expirée');\n        }\n        if (!res.ok) {\n"
    auth_new = "            recordApiDiagnostic(path, { status: res.status, error: data.error || 'Session expirée', route: apiRoute, bridge: apiBridge });\n            throw new Error(data.error || 'Session expirée');\n        }\n        if (!res.ok) {\n"
    assert auth_old in app, 'api 401 block missing'
    app = app.replace(auth_old, auth_new, 1)

    error_old = "            setSyncStatus('off');\n            throw new Error(data.error || `Erreur ${res.status}`);\n        }\n        setSyncStatus('ok');\n        return data;\n"
    error_new = "            setSyncStatus('off');\n            recordApiDiagnostic(path, { status: res.status, error: data.error || `Erreur ${res.status}`, route: apiRoute, bridge: apiBridge });\n            throw new Error(data.error || `Erreur ${res.status}`);\n        }\n        recordApiDiagnostic(path, { status: res.status, ok: true, route: apiRoute, bridge: apiBridge });\n        setSyncStatus('ok');\n        return data;\n"
    assert error_old in app, 'api error block missing'
    app = app.replace(error_old, error_new, 1)

    snap_success_old = "            const snap = await api('/api/snapshot', { method: 'GET' });\n            applySnapshot(snap);\n"
    snap_success_new = "            const snap = await api('/api/snapshot', { method: 'GET' });\n            lastSnapshotDiagnostic = null;\n            applySnapshot(snap);\n"
    assert snap_success_old in app, 'snapshot success anchor missing'
    app = app.replace(snap_success_old, snap_success_new, 1)

    snap_catch_old = "        catch (e) {\n            if (!quiet)\n                toast(e.message);\n            return false;\n        }\n        finally {\n            syncing = false;\n        }\n    }\n    async function mutate"
    snap_catch_new = "        catch (e) {\n            lastSnapshotDiagnostic = Object.assign({}, lastApiDiagnostic || {}, { message: String((e && e.message) || e || 'Erreur snapshot'), at: new Date().toISOString() });\n            if (!quiet)\n                toast(e.message);\n            return false;\n        }\n        finally {\n            syncing = false;\n        }\n    }\n    async function mutate"
    assert snap_catch_old in app, 'snapshot catch block missing'
    app = app.replace(snap_catch_old, snap_catch_new, 1)

    boot_anchor = "    async function init() {\n"
    assert boot_anchor in app, 'init anchor missing'
    diag_function = """    /* WFGG_TRAIN_INLINE_SENTINEL_BOOT_V15
       Le diagnostic de panne est rendu par app.v15 lui-même, donc il reste
       visible même si l'overlay ou le lanceur Sentinel séparé ne s'ouvre pas.
       Les contrôles viennent du Sentinel serveur existant et restent READONLY. */
    async function renderInlineSentinelBootV15(panel) {
        const host = panel && panel.querySelector('#wfggTrainInlineSentinelV15');
        if (!host)
            return;
        const lines = ['WFGG_SENTINEL_BOOT_INLINE_V15'];
        const local = lastSnapshotDiagnostic || lastApiDiagnostic || {};
        lines.push(`Snapshot navigateur: ${local.status ? 'HTTP ' + local.status : 'sans réponse'} · ${local.error || local.message || 'échec sans détail'}`);
        if (local.route)
            lines.push(`Route edge: ${local.route}`);
        if (local.bridge)
            lines.push(`Bridge: ${local.bridge}`);
        host.textContent = lines.join('\\n') + '\\nSentinel serveur: analyse en cours…';

        const portalToken = localStorage.getItem('wfgg_portal_session') || '';
        if (!portalToken) {
            lines.push('Sentinel serveur: jeton Portail navigateur absent');
            host.textContent = lines.join('\\n');
            return;
        }
        try {
            const response = await fetch('/portal-api/sentinel/run?boot=' + Date.now(), {
                method: 'GET',
                headers: { 'Authorization': 'Bearer ' + portalToken, 'Accept': 'application/json' },
                credentials: 'omit',
                cache: 'no-store'
            });
            let data = null;
            try {
                data = await response.json();
            }
            catch (_) { }
            lines.push(`Sentinel serveur: HTTP ${response.status}`);
            if (data && data.summary) {
                const c = data.summary.counts || {};
                lines.push(`Statut Sentinel: ${data.summary.status || '—'} · ok=${c.ok || 0} warning=${c.warning || 0} error=${c.error || 0}`);
            }
            const checks = Array.isArray(data && data.checks) ? data.checks : [];
            const root = checks.find(x => x && x.id === 'sentinel-root-cause');
            const snap = checks.find(x => x && x.id === 'train-snapshot');
            const roster = checks.find(x => x && x.id === 'train-access-roster');
            const selected = [];
            for (const item of [snap, roster, root, ...checks.filter(x => x && (x.level === 'error' || x.level === 'warning'))]) {
                if (!item || selected.some(x => x.id === item.id))
                    continue;
                selected.push(item);
                if (selected.length >= 8)
                    break;
            }
            for (const item of selected) {
                lines.push(`[${String(item.level || 'info').toUpperCase()}] ${item.id || 'controle'} · ${item.observed || '—'}`);
                if (item.detail)
                    lines.push(`  Détail: ${item.detail}`);
                if (item.probableCause)
                    lines.push(`  Cause: ${item.probableCause}`);
            }
            if (!response.ok && data && data.error)
                lines.push(`Erreur Sentinel: ${data.error}`);
        }
        catch (error) {
            lines.push(`Sentinel serveur: erreur réseau · ${String((error && error.message) || error)}`);
        }
        host.textContent = lines.join('\\n');
    }

"""
    app = app.replace(boot_anchor, diag_function + boot_anchor, 1)

    panel_anchor = "              document.body.appendChild(panel);\n              document.getElementById('wfggTrainBootRetryV6')?.addEventListener('click',()=>location.reload());\n            }\n"
    panel_insert = "              document.body.appendChild(panel);\n              document.getElementById('wfggTrainBootRetryV6')?.addEventListener('click',()=>location.reload());\n            }\n            let inlineSentinelHost=document.getElementById('wfggTrainInlineSentinelV15');\n            if(!inlineSentinelHost){\n              inlineSentinelHost=document.createElement('pre');\n              inlineSentinelHost.id='wfggTrainInlineSentinelV15';\n              inlineSentinelHost.style.cssText='margin:18px 0 0;padding:14px;border-radius:12px;background:#0d0c14;border:1px solid rgba(220,196,255,.28);color:#eae5f2;text-align:left;white-space:pre-wrap;word-break:break-word;font:600 12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace';\n              inlineSentinelHost.textContent='Sentinel · diagnostic en cours…';\n              panel.appendChild(inlineSentinelHost);\n            }\n            renderInlineSentinelBootV15(panel);\n"
    assert panel_anchor in app, 'boot panel anchor missing'
    app = app.replace(panel_anchor, panel_insert, 1)

old_bust = 'wfgg_bridge=v15&wfgg_ui=clean1&wfgg_auth=v7&wfgg_push=v15'
new_bust = 'wfgg_bridge=v15&wfgg_ui=clean1&wfgg_auth=v7&wfgg_push=v15&wfgg_diag=boot15'
count = worker.count(old_bust)
assert count >= 2, f'expected >=2 app cache busts, found {count}'
worker = worker.replace(old_bust, new_bust)

app_path.write_text(app)
worker_path.write_text(worker)
