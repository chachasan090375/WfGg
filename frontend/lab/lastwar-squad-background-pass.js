(() => {
  'use strict';

  const params = new URLSearchParams(location.search);
  if (params.get('layer') === 'background') {
    document.documentElement.classList.add('lw-layer-background-only');
  }

  function hydrateField(field) {
    const board = field.querySelector('.lw-formation-board');
    if (!board) return;

    const src = board.getAttribute('src');
    if (!src) return;

    // Reuse the exact extracted Last War formation scene as the blurred rear layer.
    // CSS var keeps the pass team-aware because renderFormation changes formation-N.png.
    field.style.setProperty('--lw-scene-image', `url("${src}")`);
    field.dataset.backgroundPass = '1';
  }

  function scan() {
    document.querySelectorAll('.lw-formation-field').forEach(hydrateField);
  }

  new MutationObserver(scan).observe(document.documentElement, {
    childList: true,
    subtree: true
  });

  scan();
})();
