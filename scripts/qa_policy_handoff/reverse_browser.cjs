// Synthetic, isolated full-browser QA for policy -> ZS linking.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function run() {
  const zs = process.env.FLOW_ZS_BASE_URL;
  const polis = process.env.FLOW_POLIS_BASE_URL;
  const ids = JSON.parse(fs.readFileSync(process.env.FLOW_QA_MANIFEST, 'utf8'));
  const screenshots = process.env.FLOW_QA_SCREENSHOTS;
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH && { executablePath: process.env.CHROMIUM_PATH }),
  });
  try {
    async function localPage() {
      const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
      page.setDefaultTimeout(15000);
      await page.route('**/*', route => {
        const url = new URL(route.request().url());
        if ([zs, polis].includes(url.origin)) return route.continue();
        if (screenshots && url.protocol === 'https:' &&
            ['cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com'].includes(url.hostname)) {
          return route.fallback();
        }
        return route.abort();
      });
      return page;
    }
    async function login(page, base, username, password) {
      await page.goto(base + (base === zs ? '/login/' : '/accounts/login/'));
      await page.locator('[name=username]').fill(username);
      await page.locator('[name=password]').fill(password);
      await Promise.all([page.waitForURL(url => !url.pathname.includes('/login/')),
                         page.locator('[name=password]').press('Enter')]);
    }
    async function capture(page, name) {
      if (!screenshots) return;
      await page.evaluate(() => document.fonts.ready);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({path: path.join(screenshots, name + '.png'), fullPage: true,
                             animations: 'disabled'});
    }
    async function acknowledge(page) {
      for (const field of await page.locator('input[type=checkbox]').all()) {
        if (await field.isVisible() && await field.isEnabled()) await field.check();
      }
    }
    const page = await localPage();
    await login(page, polis, 'polis-editor', process.env.FLOW_QA_POLIS_PASSWORD);
    const detail = pk => polis + '/policies/' + pk + '/';
    const choose = (pk, source) => detail(pk) + 'link-zs/' + source + '/';
    await page.goto(detail(ids.existing));
    assert.match(await page.locator('.flow-source-card').innerText(), /Связь.*не установлена/i);
    await capture(page, '01-unlinked-policy');
    await page.getByRole('link', {name: 'Подобрать сделку', exact: true}).click();
    await page.waitForURL(detail(ids.existing) + 'link-zs/');
    assert.match(await page.locator('body').innerText(), /ТС-12345\/1/);
    await capture(page, '02-suggested-deals');
    await page.locator('a[href="' + new URL(choose(ids.existing, 1)).pathname + '"]').first().click();
    await acknowledge(page);
    await page.getByRole('button', {name: 'Подтвердить привязку', exact: true}).click();
    await page.waitForURL(detail(ids.existing));
    assert.equal(await page.locator('.flow-source-card a[href="' + zs + '/summaries/1/"]').count(), 1);
    assert.equal(await page.getByRole('link', {name: 'Подобрать сделку', exact: true}).count(), 0);
    await capture(page, '03-linked-policy');

    await page.goto(detail(ids.unit));
    await page.getByRole('link', {name: 'Подобрать сделку', exact: true}).click();
    await page.locator('a[href="' + new URL(choose(ids.unit, 4)).pathname + '"]').first().click();
    await page.locator('[name=slot][value="16"]').check();
    await acknowledge(page);
    await capture(page, '04-group-confirmation');
    await page.getByRole('button', {name: 'Подтвердить привязку', exact: true}).click();
    await page.waitForURL(detail(ids.unit));
    assert.match(await page.locator('.flow-source-card').innerText(), /Объект 16 из 18/);
    await page.getByRole('link', {name: /Полисы этой группы/}).click();
    await page.waitForURL(polis + '/policies/by-summary/4/');
    assert.equal(await page.locator('table tbody tr').count(), 16);

    await page.goto(choose(ids.conflict, 4));
    const occupied = page.locator('[name=slot][value="16"]');
    assert.ok(await occupied.count() === 0 || await occupied.isDisabled(), 'occupied slot cannot be selected');
    const form = await page.locator('.flow-link-confirm-form').evaluate(el =>
      Object.fromEntries(new FormData(el)));
    form.slot = '16';
    for (const name of await page.locator('input[type=checkbox][name]').evaluateAll(els => els.map(el => el.name))) {
      form[name] = 'yes';
    }
    const blocked = await page.request.post(choose(ids.conflict, 4), {
      form, headers: {Origin: polis, Referer: choose(ids.conflict, 4)}, maxRedirects: 0,
    });
    assert.equal(blocked.status(), 409, 'occupied slot POST must report conflict');

    await page.goto(detail(ids.manual) + 'link-zs/?q=54321');
    await page.locator('a[href="' + new URL(choose(ids.manual, 3)).pathname + '"]').first().click();
    await acknowledge(page);
    await page.getByRole('button', {name: 'Подтвердить привязку', exact: true}).click();
    await page.waitForURL(detail(ids.manual));

    const reader = await localPage();
    await login(reader, polis, 'polis-reader', process.env.FLOW_QA_POLIS_PASSWORD);
    await reader.goto(detail(ids.conflict));
    assert.equal(await reader.locator('.flow-source-card').count(), 1);
    assert.equal(await reader.getByRole('link', {name: 'Подобрать сделку', exact: true}).count(), 0);
    assert.equal((await reader.request.get(detail(ids.conflict) + 'link-zs/')).status(), 403);
    assert.equal((await reader.request.get(choose(ids.conflict, 4))).status(), 403);
    const csrf = (await reader.context().cookies(polis)).find(c => c.name === 'csrftoken');
    assert.ok(csrf);
    const forbidden = await reader.request.post(choose(ids.conflict, 4), {
      form: {...form, csrfmiddlewaretoken: csrf.value},
      headers: {Origin: polis, Referer: choose(ids.conflict, 4)}, maxRedirects: 0,
    });
    assert.equal(forbidden.status(), 403);
    assert.doesNotMatch(await forbidden.text(), /CSRF verification failed|Проверка CSRF не удалась/i);
    await reader.goto(detail(ids.unit));
    assert.equal(await reader.getByRole('link', {name: /Полисы этой группы/}).count(), 1);
    await reader.getByRole('link', {name: /Полисы этой группы/}).click();
    assert.equal(await reader.locator('table tbody tr').count(), 16);

    await login(page, zs, 'zs-operator', process.env.FLOW_QA_ZS_PASSWORD);
    for (const suffix of ['', 'deal-summary/']) {
      await page.goto(zs + '/summaries/1/' + suffix);
      assert.equal(await page.locator('.policy-handoff__open').getAttribute('href'), detail(ids.existing));
    }
    await page.goto(zs + '/summaries/4/');
    assert.equal(await page.locator('.policy-handoff__open').getAttribute('href'), polis + '/policies/by-summary/4/');
    console.log('Browser PASS: editor starts in Policies, matches DFA, links existing/group/manual; reader views but cannot link; ZS sees links.');
  } finally {
    await browser.close();
  }
}
run().catch(error => { console.error(error); process.exitCode = 1; });
