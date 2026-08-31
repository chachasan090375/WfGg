(() => {
  const $ = (id) => document.getElementById(id);
  const loadingPanel = $('loadingPanel');
  const emptyPanel = $('emptyPanel');
  const viewerPanel = $('viewerPanel');
  const resultsPanel = $('resultsPanel');
  const mainImage = $('mainImage');
  const stage = $('stage');
  const imageViewport = $('imageViewport');
  const counter = $('counter');
  const voteCounter = $('voteCounter');
  const fileName = $('fileName');
  const dimensions = $('dimensions');
  const identity = $('identity');
  const format = $('format');
  const thumbStrip = $('thumbStrip');
  const fitButton = $('fitButton');
  const yesButton = $('yesButton');
  const noButton = $('noButton');
  const yesGrid = $('yesGrid');
  const resultsSummary = $('resultsSummary');
  const STORAGE_KEY = 'wfgg-lastwar-formation-fixed-texture-review-v1';

  let items = [];
  let index = 0;
  let fitMode = true;
  let touchStartX = null;
  let touchStartY = null;

  function itemKey(item) {
    return `${item.bundleId}:${item.pathID}:${item.sha256 || item.src}`;
  }

  function loadVotes() {
    try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {}; }
    catch { return {}; }
  }

  function saveVotes() {
    const votes = {};
    for (const item of items) {
      if (item.vote === 'yes' || item.vote === 'no') votes[itemKey(item)] = item.vote;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify(votes));
  }

  async function loadManifest() {
    try {
      const response = await fetch('/lab/formation-texture-review/manifest.json', { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const manifest = await response.json();
      const list = Array.isArray(manifest.items) ? manifest.items : [];
      if (!list.length) throw new Error('manifest empty');
      const votes = loadVotes();
      items = list.map((item) => ({ ...item, vote: votes[itemKey(item)] || null, thumb: null }));
      loadingPanel.classList.add('hidden');
      viewerPanel.classList.remove('hidden');
      buildThumbs();
      const firstUnvoted = items.findIndex((item) => !item.vote);
      index = firstUnvoted >= 0 ? firstUnvoted : 0;
      render();
      if (items.every((item) => item.vote)) showResults();
    } catch (error) {
      $('loadingText').textContent = `Lot indisponible : ${error.message}`;
      loadingPanel.classList.add('hidden');
      emptyPanel.classList.remove('hidden');
    }
  }

  function buildThumbs() {
    const frag = document.createDocumentFragment();
    items.forEach((item, i) => {
      const button = document.createElement('button');
      button.className = 'thumb';
      button.type = 'button';
      button.dataset.index = String(i);
      button.title = item.name || item.file || `Texture ${i + 1}`;
      const img = document.createElement('img');
      img.src = item.src;
      img.alt = '';
      img.loading = 'lazy';
      button.appendChild(img);
      button.addEventListener('click', () => goTo(i));
      item.thumb = button;
      frag.appendChild(button);
    });
    thumbStrip.replaceChildren(frag);
  }

  function render() {
    if (!items.length) return;
    const item = items[index];
    mainImage.src = item.src;
    mainImage.alt = item.name || `Texture ${index + 1}`;
    counter.textContent = `${index + 1} / ${items.length}`;
    fileName.textContent = item.name || item.file || 'Sans nom';
    dimensions.textContent = `${item.width} × ${item.height} px`;
    identity.textContent = `bundle ${item.bundleId} · pathID ${item.pathID}`;
    format.textContent = item.textureFormat || '—';

    yesButton.classList.toggle('active', item.vote === 'yes');
    noButton.classList.toggle('active', item.vote === 'no');

    items.forEach((entry, i) => {
      if (!entry.thumb) return;
      entry.thumb.classList.toggle('active', i === index);
      entry.thumb.classList.toggle('vote-yes', entry.vote === 'yes');
      entry.thumb.classList.toggle('vote-no', entry.vote === 'no');
    });
    if (item.thumb) item.thumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    imageViewport.scrollTo({ left: 0, top: 0 });
    updateProgress();
  }

  function updateProgress() {
    const reviewed = items.filter((item) => item.vote).length;
    voteCounter.textContent = `${reviewed} examinée${reviewed > 1 ? 's' : ''} / ${items.length}`;
  }

  function goTo(nextIndex) {
    if (!items.length) return;
    index = (nextIndex + items.length) % items.length;
    resultsPanel.classList.add('hidden');
    viewerPanel.classList.remove('hidden');
    render();
  }

  function nextUnvoted(afterIndex) {
    for (let step = 1; step <= items.length; step += 1) {
      const i = (afterIndex + step) % items.length;
      if (!items[i].vote) return i;
    }
    return -1;
  }

  function vote(value) {
    if (!items.length) return;
    items[index].vote = value;
    saveVotes();
    updateProgress();
    const nextIndex = nextUnvoted(index);
    if (nextIndex === -1) showResults();
    else goTo(nextIndex);
  }

  function showResults() {
    saveVotes();
    const yes = items.filter((item) => item.vote === 'yes');
    viewerPanel.classList.add('hidden');
    resultsPanel.classList.remove('hidden');
    resultsSummary.textContent = `${yes.length} image${yes.length > 1 ? 's' : ''} retenue${yes.length > 1 ? 's' : ''} sur ${items.length}.`;
    const frag = document.createDocumentFragment();
    yes.forEach((item) => {
      const card = document.createElement('article');
      card.className = 'yes-card';
      const img = document.createElement('img');
      img.src = item.src;
      img.alt = item.name || 'Texture retenue';
      const meta = document.createElement('div');
      meta.innerHTML = `<strong></strong><span>${item.width}×${item.height} · b${item.bundleId} · p${item.pathID}</span>`;
      meta.querySelector('strong').textContent = item.name || item.file || 'Sans nom';
      card.append(img, meta);
      frag.appendChild(card);
    });
    yesGrid.replaceChildren(frag);
    $('copyYesButton').disabled = yes.length === 0;
  }

  async function copyYes() {
    const yes = items.filter((item) => item.vote === 'yes');
    if (!yes.length) return;
    const text = yes.map((item) => `${item.name || item.file} — ${item.width}x${item.height} — bundle=${item.bundleId} pathID=${item.pathID} format=${item.textureFormat || '-'}`).join('\n');
    try {
      await navigator.clipboard.writeText(text);
      const old = $('copyYesButton').textContent;
      $('copyYesButton').textContent = 'Copié ✓';
      setTimeout(() => { $('copyYesButton').textContent = old; }, 1200);
    } catch {
      window.prompt('Copie cette sélection :', text);
    }
  }

  function toggleFit() {
    fitMode = !fitMode;
    stage.classList.toggle('fit-mode', fitMode);
    stage.classList.toggle('native-mode', !fitMode);
    fitButton.textContent = fitMode ? 'Ajuster' : 'Taille réelle';
    imageViewport.scrollTo({ left: 0, top: 0 });
  }

  function resetVotes() {
    if (!window.confirm('Effacer tous les Oui/Non et recommencer la revue ?')) return;
    localStorage.removeItem(STORAGE_KEY);
    for (const item of items) item.vote = null;
    index = 0;
    resultsPanel.classList.add('hidden');
    viewerPanel.classList.remove('hidden');
    render();
  }

  $('prevButton').addEventListener('click', () => goTo(index - 1));
  $('nextButton').addEventListener('click', () => goTo(index + 1));
  $('prevBottom').addEventListener('click', () => goTo(index - 1));
  $('nextBottom').addEventListener('click', () => goTo(index + 1));
  yesButton.addEventListener('click', () => vote('yes'));
  noButton.addEventListener('click', () => vote('no'));
  fitButton.addEventListener('click', toggleFit);
  $('resetVotesButton').addEventListener('click', resetVotes);
  $('resumeButton').addEventListener('click', () => goTo(0));
  $('copyYesButton').addEventListener('click', copyYes);

  document.addEventListener('keydown', (event) => {
    if (viewerPanel.classList.contains('hidden')) return;
    if (event.key === 'ArrowLeft') goTo(index - 1);
    else if (event.key === 'ArrowRight') goTo(index + 1);
    else if (event.key.toLowerCase() === 'o' || event.key.toLowerCase() === 'y') vote('yes');
    else if (event.key.toLowerCase() === 'n') vote('no');
    else if (event.key.toLowerCase() === 'f') toggleFit();
  });

  imageViewport.addEventListener('touchstart', (event) => {
    const touch = event.changedTouches[0];
    touchStartX = touch.clientX;
    touchStartY = touch.clientY;
  }, { passive: true });

  imageViewport.addEventListener('touchend', (event) => {
    if (touchStartX === null || touchStartY === null) return;
    const touch = event.changedTouches[0];
    const dx = touch.clientX - touchStartX;
    const dy = touch.clientY - touchStartY;
    touchStartX = null;
    touchStartY = null;
    if (Math.abs(dx) < 55 || Math.abs(dx) < Math.abs(dy) * 1.3) return;
    goTo(index + (dx < 0 ? 1 : -1));
  }, { passive: true });

  loadManifest();
})();
