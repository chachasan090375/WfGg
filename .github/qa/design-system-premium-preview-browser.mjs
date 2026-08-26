import { chromium } from 'playwright';

const ROOT = process.env.WFGG_PREVIEW_ROOT || 'https://design-system-preview-v1.wfgg.pages.dev';

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

async function waitDesign(page) {
  await page.waitForFunction(() => window.WFGG_DESIGN_SYSTEM_PREVIEW?.version === 'v2-premium', null, { timeout: 15000 });
}

async function inspectPortal(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await page.goto(`${ROOT}/?premium_browser=1`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await waitDesign(page);

  const state = await page.evaluate(() => ({
    version: document.documentElement.dataset.wfggDesignSystem,
    rootClass: document.documentElement.className,
    font: getComputedStyle(document.body).fontFamily,
    champagne: getComputedStyle(document.documentElement).getPropertyValue('--wfgg-champagne').trim(),
    brandLogo: document.querySelector('.auth-card .brand-mark img')?.getAttribute('src') || '',
    moduleIcons: [...document.querySelectorAll('.module-card .module-icon')].map(el => ({ text: el.textContent.trim(), svg: !!el.querySelector('svg') })),
    oldV1: !!document.querySelector('link[href*="preview-v1.css"],script[src*="preview-v1.js"]'),
    badge: document.querySelector('[data-wfgg-preview-badge-v2]')?.textContent?.trim() || ''
  }));

  assert(state.version === 'preview-v2-premium', `Portal: version inattendue ${state.version}`);
  assert(state.rootClass.includes('wfgg-ds-portal-v2'), 'Portal: classe premium absente');
  assert(/SF Pro|Segoe UI Variable|Inter|Roboto|system-ui/i.test(state.font), `Portal: pile typographique inattendue ${state.font}`);
  assert(state.champagne === '#d8c69e', `Portal: champagne inattendu ${state.champagne}`);
  assert(state.brandLogo.includes('/assets/wfgg-logo-mini.svg'), `Portal: logo premium absent ${state.brandLogo}`);
  assert(state.moduleIcons.length >= 3 && state.moduleIcons.slice(0, 3).every(x => x.svg && !/[📚🚂⚙]/u.test(x.text)), `Portal: iconographie module non SVG ${JSON.stringify(state.moduleIcons)}`);
  assert(!state.oldV1, 'Portal: ancienne V1 encore chargée');
  assert(/premium|charte/i.test(state.badge), `Portal: badge preview absent ${state.badge}`);
  await context.close();
  return state.font;
}

async function inspectGuides(browser, portalFont) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await page.goto(`${ROOT}/guides/?premium_browser=1`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await waitDesign(page);
  await page.waitForTimeout(150);

  const state = await page.evaluate(() => ({
    version: document.documentElement.dataset.wfggDesignSystem,
    rootClass: document.documentElement.className,
    font: getComputedStyle(document.body).fontFamily,
    homeLogo: document.querySelector('[data-wfgg-module-home-v2] img,[data-wfgg-inline-home-v2] img')?.getAttribute('src') || '',
    homeHref: document.querySelector('[data-wfgg-module-home-v2],[data-wfgg-inline-home-v2]')?.getAttribute('href') || '',
    cardIcons: [...document.querySelectorAll('.grid>.card .icon')].map(el => ({ text: el.textContent.trim(), svg: !!el.querySelector('svg') })),
    oldV1: !!document.querySelector('link[href*="preview-v1.css"],script[src*="preview-v1.js"]')
  }));

  assert(state.version === 'preview-v2-premium', `Guides: version inattendue ${state.version}`);
  assert(state.rootClass.includes('wfgg-ds-guides-v2'), 'Guides: classe premium absente');
  assert(state.font === portalFont, `Guides: police différente du Portail ${state.font} != ${portalFont}`);
  assert(state.homeLogo.includes('/assets/wfgg-logo-mini.svg'), `Guides: logo commun absent ${state.homeLogo}`);
  assert(state.homeHref === '/' || state.homeHref.startsWith('/?'), `Guides: retour Portail incohérent ${state.homeHref}`);
  assert(state.cardIcons.length >= 2 && state.cardIcons.every(x => x.svg && !/[🌴🧭📚]/u.test(x.text)), `Guides: iconographie landing non SVG ${JSON.stringify(state.cardIcons)}`);
  assert(!state.oldV1, 'Guides: ancienne V1 encore chargée');
  await context.close();
}

async function inspectTrain(browser, portalFont) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, deviceScaleFactor: 2 });
  const page = await context.newPage();
  await page.goto(`${ROOT}/train/?premium_browser=1`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await waitDesign(page);
  await page.waitForTimeout(250);

  const state = await page.evaluate(() => ({
    version: document.documentElement.dataset.wfggDesignSystem,
    rootClass: document.documentElement.className,
    font: getComputedStyle(document.body).fontFamily,
    home: (() => {
      const el = document.querySelector('#brandHome[data-wfgg-module-home-v2],[data-wfgg-module-home-v2]');
      return { exists: !!el, href: el?.getAttribute('href') || '', logo: el?.querySelector('img')?.getAttribute('src') || '', svg: !!el?.querySelector('svg') };
    })(),
    visibleEmojiHeadings: [...document.querySelectorAll('h1,h2,h3,.section-title h2,.section-title h3')]
      .filter(el => getComputedStyle(el).display !== 'none' && el.getClientRects().length)
      .map(el => el.textContent.trim())
      .filter(text => /^[📚🚂🚆⚙👤ℹ🔎🔍📅🗓🔔📊📈👥🔁🧾🎓🔗⭐✉🧭🌴]/u.test(text)),
    oldV1: !!document.querySelector('link[href*="preview-v1.css"],script[src*="preview-v1.js"]')
  }));

  assert(state.version === 'preview-v2-premium', `Train: version inattendue ${state.version}`);
  assert(state.rootClass.includes('wfgg-ds-train-v2'), 'Train: classe premium absente');
  assert(state.font === portalFont, `Train: police différente du Portail ${state.font} != ${portalFont}`);
  assert(state.home.exists && state.home.logo.includes('/assets/wfgg-logo-mini.svg') && state.home.svg, `Train: retour Portail premium incomplet ${JSON.stringify(state.home)}`);
  assert(state.visibleEmojiHeadings.length === 0, `Train: titres principaux encore en emoji ${JSON.stringify(state.visibleEmojiHeadings)}`);
  assert(!state.oldV1, 'Train: ancienne V1 encore chargée');
  await context.close();
}

const browser = await chromium.launch({ headless: true });
try {
  const font = await inspectPortal(browser);
  await inspectGuides(browser, font);
  await inspectTrain(browser, font);
  console.log('WFGG_PREMIUM_BROWSER_PORTAL=OK');
  console.log('WFGG_PREMIUM_BROWSER_GUIDES=OK');
  console.log('WFGG_PREMIUM_BROWSER_TRAIN=OK');
} finally {
  await browser.close();
}
