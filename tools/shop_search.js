#!/usr/bin/env node
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const site = (process.argv[2] || 'ali').toLowerCase();
const query = process.argv[3] || '2x20 stackable header 2.54mm';
const maxResults = parseInt(process.argv[4]) || 8;

const COOKIE_DIR = path.join(process.env.HOME, '.config', 'shop_cookies');

function loadCookies(site, domain) {
  const file = path.join(COOKIE_DIR, `${site}.txt`);
  if (!fs.existsSync(file)) return [];
  const raw = fs.readFileSync(file, 'utf8').trim();
  return raw.split(';').map(pair => {
    const [name, ...rest] = pair.trim().split('=');
    return { name: name.trim(), value: rest.join('='), domain };
  }).filter(c => c.name && c.value);
}

const sites = {
  ali: {
    name: 'AliExpress',
    domain: '.aliexpress.com',
    searchUrl: (q) => `https://www.aliexpress.com/w/wholesale-${encodeURIComponent(q).replace(/%20/g, '-')}.html`,
    homeUrl: 'https://www.aliexpress.com',
    extract: (max) => {
      const results = [];
      const links = document.querySelectorAll('a[href*="/item/"]');
      const seen = new Set();
      for (const link of links) {
        if (results.length >= max) break;
        const match = link.href.match(/\/item\/(\d+)/);
        if (!match || seen.has(match[1])) continue;
        seen.add(match[1]);
        let card = link.closest('[class*="Card"], [class*="card"], [class*="Item"], [class*="item"]') || link.parentElement?.parentElement;
        let title = link.title || link.textContent?.trim();
        if (!title || title.length < 10) {
          const h3 = card?.querySelector('h3') || card?.querySelector('[class*="title"]');
          if (h3) title = h3.textContent.trim();
        }
        let price = '';
        const priceEl = card?.querySelector('[class*="price"], [class*="Price"]');
        if (priceEl) price = priceEl.textContent.trim().replace(/\s+/g, ' ');
        if (title && title.length > 10) {
          results.push({
            title: title.slice(0, 120),
            price: price.slice(0, 30),
            url: `https://www.aliexpress.com/item/${match[1]}.html`
          });
        }
      }
      return results;
    }
  },
  amazon: {
    name: 'Amazon FR',
    domain: '.amazon.fr',
    searchUrl: (q) => `https://www.amazon.fr/s?k=${encodeURIComponent(q)}`,
    homeUrl: null,
    extract: (max) => {
      const results = [];
      const items = document.querySelectorAll('[data-asin]:not([data-asin=""])');
      for (const item of items) {
        if (results.length >= max) break;
        const asin = item.getAttribute('data-asin');
        if (!asin || asin.length < 5) continue;
        const titleEl = item.querySelector('h2 a span, h2 span');
        if (!titleEl) continue;
        const title = titleEl.textContent.trim();
        if (title.length < 10) continue;
        let price = '';
        const priceEl = item.querySelector('.a-price .a-offscreen');
        if (priceEl) price = priceEl.textContent.trim();
        const linkEl = item.querySelector('h2 a');
        const url = linkEl ? `https://www.amazon.fr${linkEl.getAttribute('href')?.split('?')[0] || `/dp/${asin}`}` : `https://www.amazon.fr/dp/${asin}`;
        results.push({ title: title.slice(0, 120), price, url });
      }
      return results;
    }
  }
};

const config = sites[site];
if (!config) {
  console.error(`Usage: shop_search.js [ali|amazon] "search query" [max_results]`);
  console.error(`Cookie files: ~/.config/shop_cookies/ali.txt, amazon.txt`);
  process.exit(1);
}

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-blink-features=AutomationControlled',
      '--disable-infobars',
      '--window-size=1280,800'
    ]
  });

  const page = await browser.newPage();
  await page.evaluateOnNewDocument(() => {
    Object.defineProperty(navigator, 'webdriver', { get: () => false });
    window.chrome = { runtime: {} };
    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3] });
    Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en', 'fr'] });
  });
  await page.setUserAgent('Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36');
  await page.setViewport({ width: 1280, height: 800 });
  await page.setExtraHTTPHeaders({ 'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8' });

  // Load cookies if available
  const cookies = loadCookies(site, config.domain);
  if (cookies.length > 0) {
    await page.setCookie(...cookies);
    console.error(`Loaded ${cookies.length} cookies from ${COOKIE_DIR}/${site}.txt`);
  }

  if (config.homeUrl) {
    console.error(`Loading ${config.name} homepage...`);
    await page.goto(config.homeUrl, { waitUntil: 'networkidle2', timeout: 30000 });
    await new Promise(r => setTimeout(r, 2000));
  }

  const url = config.searchUrl(query);
  console.error(`Searching ${config.name}: ${query}`);
  await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 });
  await new Promise(r => setTimeout(r, 3000));

  const title = await page.title();
  if (title.toLowerCase().includes('captcha') || title.toLowerCase().includes('robot')) {
    console.log(`Blocked by CAPTCHA on ${config.name}.`);
    await page.screenshot({ path: '/tmp/shop_debug.png' });
    console.error('Debug screenshot: /tmp/shop_debug.png');
    await browser.close();
    process.exit(1);
  }

  const products = await page.evaluate(config.extract, maxResults);

  console.log(`\n=== ${config.name} results for "${query}" ===\n`);
  for (let i = 0; i < products.length; i++) {
    console.log(`${i + 1}. ${products[i].title}`);
    console.log(`   Price: ${products[i].price || 'N/A'}`);
    console.log(`   ${products[i].url}`);
    console.log('');
  }

  if (products.length === 0) {
    console.log('No products found.');
    await page.screenshot({ path: '/tmp/shop_debug.png' });
    console.error('Debug screenshot: /tmp/shop_debug.png');
  }

  console.error(`Found ${products.length} results`);
  await browser.close();
})();
