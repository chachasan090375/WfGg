from pathlib import Path

path=Path('frontend/_worker.js')
src=path.read_text(encoding='utf-8')

old="""      const value = element.getAttribute(attr);
      if (!value) continue;

      if (value.startsWith('/') && !value.startsWith('//')) {
"""
new="""      const value = element.getAttribute(attr);
      if (!value) continue;

      /* WFGG_TRAIN_RELATIVE_APP_CACHE_BUST_V1
         L'upstream Train référence aussi app.js relativement à /train/.
         Versionner ce cas avant la réécriture des chemins absolus.
      */
      if (
        this.prefix === '/train' &&
        attr === 'src' &&
        /^(?:\\.\\/)?app\\.js(?:[?#]|$)/i.test(value)
      ) {
        const versioned =
          value +
          (value.includes('?') ? '&' : '?') +
          'wfgg_bridge=v6';
        element.setAttribute(attr, versioned);
        continue;
      }

      if (value.startsWith('/') && !value.startsWith('//')) {
"""

if old not in src:
    raise SystemExit('Expected RootAttributeRewriter insertion point not found')
src=src.replace(old,new,1)
path.write_text(src,encoding='utf-8')
print('TRAIN_RELATIVE_APP_CACHE_PATCH=OK')
