(() => {
  const $ = (id) => document.getElementById(id);
  const loaderPanel = $('loaderPanel');
  const viewerPanel = $('viewerPanel');
  const filePicker = $('filePicker');
  const folderPicker = $('folderPicker');
  const mainImage = $('mainImage');
  const stage = $('stage');
  const imageViewport = $('imageViewport');
  const counter = $('counter');
  const markedCounter = $('markedCounter');
  const fileName = $('fileName');
  const dimensions = $('dimensions');
  const fileSize = $('fileSize');
  const thumbStrip = $('thumbStrip');
  const markButton = $('markButton');
  const fitButton = $('fitButton');
  const copySelectionButton = $('copySelectionButton');
  const selectionText = $('selectionText');

  let items = [];
  let index = 0;
  let fitMode = true;
  let touchStartX = null;
  let touchStartY = null;

  const naturalCompare = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });

  function cleanup() {
    for (const item of items) {
      if (item.url) URL.revokeObjectURL(item.url);
    }
    items = [];
    thumbStrip.replaceChildren();
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return '—';
    if (bytes < 1024) return `${bytes} o`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} Mo`;
  }

  function isImage(file) {
    return file && (file.type.startsWith('image/') || /\.(png|jpe?g|webp)$/i.test(file.name));
  }

  async function loadFiles(fileList) {
    const files = Array.from(fileList || []).filter(isImage);
    if (!files.length) return;

    cleanup();
    files.sort((a, b) => naturalCompare.compare(a.webkitRelativePath || a.name, b.webkitRelativePath || b.name));

    items = files.map((file) => ({
      file,
      name: file.webkitRelativePath || file.name,
      url: URL.createObjectURL(file),
      width: null,
      height: null,
      marked: false,
      thumb: null,
    }));

    index = 0;
    loaderPanel.classList.add('hidden');
    viewerPanel.classList.remove('hidden');
    buildThumbs();
    render();
  }

  function buildThumbs() {
    const frag = document.createDocumentFragment();
    items.forEach((item, i) => {
      const button = document.createElement('button');
      button.className = 'thumb';
      button.type = 'button';
      button.dataset.index = String(i);
      button.title = item.name;
      button.setAttribute('aria-label', `Afficher ${item.name}`);

      const img = document.createElement('img');
      img.src = item.url;
      img.alt = '';
      img.loading = 'lazy';
      button.appendChild(img);
      button.addEventListener('click', () => goTo(i));
      item.thumb = button;
      frag.appendChild(button);
    });
    thumbStrip.appendChild(frag);
  }

  function render() {
    if (!items.length) return;
    const item = items[index];

    mainImage.onload = () => {
      item.width = mainImage.naturalWidth;
      item.height = mainImage.naturalHeight;
      dimensions.textContent = `${item.width} × ${item.height} px`;
    };
    mainImage.src = item.url;

    counter.textContent = `${index + 1} / ${items.length}`;
    fileName.textContent = item.name;
    dimensions.textContent = item.width && item.height ? `${item.width} × ${item.height} px` : 'lecture des dimensions…';
    fileSize.textContent = formatBytes(item.file.size);

    markButton.classList.toggle('active', item.marked);
    markButton.setAttribute('aria-pressed', item.marked ? 'true' : 'false');
    markButton.textContent = item.marked ? '★ Candidate' : '☆ Candidat';

    items.forEach((entry, i) => {
      if (!entry.thumb) return;
      entry.thumb.classList.toggle('active', i === index);
      entry.thumb.classList.toggle('marked', entry.marked);
    });

    const activeThumb = item.thumb;
    if (activeThumb) activeThumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });

    imageViewport.scrollTo({ left: 0, top: 0 });
    updateSelection();
  }

  function goTo(nextIndex) {
    if (!items.length) return;
    index = (nextIndex + items.length) % items.length;
    render();
  }

  function previous() { goTo(index - 1); }
  function next() { goTo(index + 1); }

  function toggleMark() {
    if (!items.length) return;
    items[index].marked = !items[index].marked;
    render();
  }

  function updateSelection() {
    const marked = items.filter((item) => item.marked);
    markedCounter.textContent = `${marked.length} candidat${marked.length > 1 ? 's' : ''}`;
    copySelectionButton.disabled = marked.length === 0;

    if (!marked.length) {
      selectionText.textContent = 'Aucune candidate marquée.';
      return;
    }

    const names = marked.map((item) => item.name);
    selectionText.textContent = names.length <= 3 ? names.join(' · ') : `${names.slice(0, 3).join(' · ')} · +${names.length - 3}`;
  }

  async function copySelection() {
    const marked = items.filter((item) => item.marked);
    if (!marked.length) return;
    const text = marked.map((item) => {
      const size = item.width && item.height ? ` — ${item.width}x${item.height}` : '';
      return `${item.name}${size}`;
    }).join('\n');

    try {
      await navigator.clipboard.writeText(text);
      const old = copySelectionButton.textContent;
      copySelectionButton.textContent = 'Copié ✓';
      setTimeout(() => { copySelectionButton.textContent = old; }, 1200);
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

  function resetPicker() {
    loaderPanel.classList.remove('hidden');
    viewerPanel.classList.add('hidden');
    filePicker.value = '';
    folderPicker.value = '';
  }

  filePicker.addEventListener('change', (event) => loadFiles(event.target.files));
  folderPicker.addEventListener('change', (event) => loadFiles(event.target.files));
  $('prevButton').addEventListener('click', previous);
  $('nextButton').addEventListener('click', next);
  $('prevBottom').addEventListener('click', previous);
  $('nextBottom').addEventListener('click', next);
  markButton.addEventListener('click', toggleMark);
  fitButton.addEventListener('click', toggleFit);
  copySelectionButton.addEventListener('click', copySelection);
  $('reloadButton').addEventListener('click', resetPicker);

  document.addEventListener('keydown', (event) => {
    if (viewerPanel.classList.contains('hidden')) return;
    if (event.key === 'ArrowLeft') previous();
    else if (event.key === 'ArrowRight') next();
    else if (event.key === ' ' || event.key.toLowerCase() === 'm') {
      event.preventDefault();
      toggleMark();
    }
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
    if (dx < 0) next(); else previous();
  }, { passive: true });

  window.addEventListener('beforeunload', cleanup);
})();
