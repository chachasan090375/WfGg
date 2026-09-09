from pathlib import Path
p=Path('frontend/_worker.js')
s=p.read_text(encoding='utf-8')
if 'WFGG_TRAIN_PUSH_MANIFEST_HEAD_V1' not in s:
    old="""        let html = languageBridgeScript(options.routeName || route.prefix.slice(1));
        if (options.baseHref) {"""
    new="""        let html = languageBridgeScript(options.routeName || route.prefix.slice(1));
        /* WFGG_TRAIN_PUSH_MANIFEST_HEAD_V1 */
        if (options.routeName === 'train') {
          html = '<link rel=\"manifest\" href=\"/train/manifest.webmanifest\"><meta name=\"apple-mobile-web-app-capable\" content=\"yes\"><meta name=\"apple-mobile-web-app-status-bar-style\" content=\"black-translucent\"><meta name=\"theme-color\" content=\"#00182b\">' + html;
        }
        if (options.baseHref) {"""
    if old not in s: raise SystemExit('head anchor missing')
    s=s.replace(old,new,1)
p.write_text(s,encoding='utf-8')
print('Train manifest metadata injected')
