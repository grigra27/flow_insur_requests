// Normal staff UI, two origins, independent Django sessions and real service-to-service requests.
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function run() {
  const zs = process.env.FLOW_ZS_BASE_URL;
  const polis = process.env.FLOW_POLIS_BASE_URL;
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH && { executablePath: process.env.CHROMIUM_PATH }),
  });
  async function localPage() {
    const tab = await browser.newPage();
    tab.setDefaultTimeout(12000);
    await tab.route('**/*', route => {
      const origin = new URL(route.request().url()).origin;
      return [zs, polis].includes(origin) ? route.continue() : route.abort();
    });
    return tab;
  }
  const page = await localPage();

  async function login(tab, username, password) {
    await tab.locator('[name=username]').fill(username);
    await tab.locator('[name=password]').fill(password);
    await Promise.all([tab.waitForURL(url => !url.pathname.includes('/login/')),
                      tab.locator('[name=password]').press('Enter')]);
  }
  async function start(id, tab=page) {
    await tab.goto(zs + '/summaries/' + id + '/deal-summary/');
    await tab.getByRole('button', {name: 'Создать полис', exact: true}).click();
    await tab.waitForURL(url => url.origin === polis);
  }
  async function checkReader(reviewUrl, linkedPolicy) {
    const tab = await localPage(); // browser.newPage creates an isolated cookie jar
    try {
      await tab.goto(zs + '/login/');
      await login(tab, 'zs-colleague', process.env.FLOW_QA_ZS_PASSWORD);
      await start(2, tab);
      await tab.waitForURL(url => url.origin === polis && url.pathname.endsWith('/login/'));
      await Promise.all([
        tab.waitForResponse(r => r.url().startsWith(polis + '/flow/') && r.status() === 403),
        login(tab, 'polis-reader', process.env.FLOW_QA_POLIS_PASSWORD),
      ]);
      const denial = await tab.locator('body').innerText();
      assert.match(denial, /нет прав[^.\n]{0,100}созда/iu, denial);
      assert.equal(await tab.locator('#id_policy_number').count(), 0);
      const csrf = (await tab.context().cookies(polis)).find(c => c.name === 'csrftoken');
      assert.ok(csrf, 'use a legitimate reader CSRF token to check authorization');
      for (const action of ['new', 'link']) {
        const response = await tab.request.post(reviewUrl, {
          form: {action, slot: '0', policy_id: '1', candidates: '1', csrfmiddlewaretoken: csrf.value},
          headers: {Origin: polis, Referer: polis + '/'}, maxRedirects: 0,
        });
        assert.equal(response.status(), 403, 'reader POST: ' + action);
        assert.doesNotMatch(await response.text(), /CSRF verification failed|Проверка CSRF не удалась/i);
      }
      const journal = await tab.goto(polis + '/policies/');
      assert.equal(journal.status(), 200, 'reader keeps normal access to the policy register');
      await tab.context().clearCookies({domain: new URL(polis).hostname});
      await tab.goto(zs + '/summaries/1/');
      await tab.getByRole('link', {name: /Открыть полис.*QA-NEW/}).click();
      await tab.waitForURL(url => url.origin === polis && url.pathname.endsWith('/login/'));
      await login(tab, 'polis-reader', process.env.FLOW_QA_POLIS_PASSWORD);
      await tab.waitForURL(linkedPolicy);
      console.log('Browser PASS: reader gets a permission message, cannot create or link by POST, and can open an existing policy after login');
    } finally {
      await tab.close();
    }
  }
  async function save(number) {
    const first = new Date().getFullYear() + 1;
    await page.locator('#id_policy_number').fill(number);
    await page.locator('#id_start_date').fill('01.01.' + first);
    await page.locator('#id_end_date').fill('31.12.' + (first + 1));
    const rows = page.locator('input[name^=payment_schedule-][name$="-due_date"]:not([name*=__prefix__])');
    assert.equal(await rows.count(), 3, 'all installment rows must be visible');
    for (const [index, date] of ['01.01.' + first, '01.07.' + first, '01.01.' + (first+1)].entries()) {
      await rows.nth(index).fill(date);
    }
    if (number === 'QA-SEPARATE') {
      assert.ok(!(await page.locator('#id_policyholder').inputValue()), 'lessor needs explicit choice');
      await page.locator('[name="payment_schedule-0-kv_rub"]').fill('12.34');
    }
    await page.getByRole('button', {name: 'Сохранить полис и связать со сводом'}).last().click();
    await page.waitForURL(url => /^\/policies\/\d+\/$/.test(url.pathname));
    assert.ok((await page.locator('body').innerText()).includes(number));
    return page.url();
  }
  async function verifyRoundtrip(id, number, target) {
    const back = page.locator('a[href="' + zs + '/summaries/' + id + '/"]');
    await back.first().click();
    await page.waitForURL(zs + '/summaries/' + id + '/');
    const policy = page.getByRole('link', {name: new RegExp('Открыть полис.*' + number)});
    assert.equal(await policy.getAttribute('href'), target);
    await policy.click();
    await page.waitForURL(target);
  }

  try {
    await page.goto(zs + '/login/');
    await login(page, 'zs-operator', process.env.FLOW_QA_ZS_PASSWORD);
    await start(1);
    await page.waitForURL(url => url.origin === polis && url.pathname.endsWith('/login/'));
    await login(page, 'polis-editor', process.env.FLOW_QA_POLIS_PASSWORD);
    await page.waitForSelector('#id_policy_number');
    const created = await save('QA-NEW');
    await verifyRoundtrip(1, 'QA-NEW', created);
    console.log('Browser PASS: new policy, separate login, two annual offers and reverse links');

    await start(2);
    await page.getByRole('radio', {name: 'Выбрать полис QA-OLD'}).waitFor();
    await checkReader(page.url(), created);
    await page.getByRole('radio', {name: 'Выбрать полис QA-OLD'}).check();
    await page.getByRole('button', {name: /Связать.*полис/}).click();
    await page.waitForURL(url => /^\/policies\/\d+\/$/.test(url.pathname));
    const existing = page.url();
    await verifyRoundtrip(2, 'QA-OLD', existing);
    console.log('Browser PASS: explicitly selected the existing policy');

    await start(3);
    assert.ok(await page.getByRole('radio', {name: 'Выбрать полис QA-OLD'}).isVisible());
    await page.getByRole('button', {name: 'Создать отдельный полис', exact: true}).click();
    const separate = await save('QA-SEPARATE');
    assert.notEqual(separate, existing);
    await verifyRoundtrip(3, 'QA-SEPARATE', separate);
    console.log('Browser PASS: separate policy despite an existing policy on the same DFA');
  } catch (error) {
    console.error('Location:', new URL(page.url()).pathname);
    console.error('Page feedback:', (await page.locator('h1, h2, .errorlist, .errornote, .alert, [role=alert]').allTextContents()).join(' | ').slice(0, 2000));
    throw error;
  } finally {
    await browser.close();
  }
}
run().catch(error => { console.error(error.message); process.exitCode = 1; });
