// Normal staff UI, two origins, independent Django sessions and real service-to-service requests.
const assert = require('node:assert/strict');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function run() {
  const zs = process.env.FLOW_ZS_BASE_URL;
  const polis = process.env.FLOW_POLIS_BASE_URL;
  const screenshots = process.env.FLOW_QA_SCREENSHOTS;
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH && { executablePath: process.env.CHROMIUM_PATH }),
  });
  async function localPage() {
    const tab = await browser.newPage();
    tab.setDefaultTimeout(12000);
    await tab.route('**/*', route => {
      const url = new URL(route.request().url());
      if ([zs, polis].includes(url.origin)) return route.continue();
      const publicAssets = ['cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com'];
      if (screenshots && url.protocol === 'https:' && publicAssets.includes(url.hostname)) return route.fallback();
      return route.abort();
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
  async function checkReader(reviewUrl, linkedPolicy, formUrl) {
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
      assert.equal((await tab.request.get(formUrl)).status(), 403);
      const forbiddenSave = await tab.request.post(formUrl, {
        form: {csrfmiddlewaretoken: csrf.value}, headers: {Origin: polis, Referer: formUrl},
      });
      assert.equal(forbiddenSave.status(), 403);
      assert.doesNotMatch(await forbiddenSave.text(), /CSRF verification failed|Проверка CSRF не удалась/i);
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
  async function fillRequisites(number) {
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
      const commission = page.locator('[name="payment_schedule-0-kv_rub"]');
      if (!(await commission.isVisible())) await page.locator('[data-flow-extra-payments]').check();
      await commission.fill('12.34');
    }
  }
  async function save(number) {
    await fillRequisites(number);
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

  async function capture(label, action, desktopOnly = false) {
    if (!screenshots) return;
    const original = page.viewportSize();
    try {
      await page.evaluate(() => document.fonts.ready);
      const sizes = [['desktop', 1440, 900]];
      if (!desktopOnly) sizes.push(['mobile', 390, 844]);
      for (const [name, width, height] of sizes) {
        await page.setViewportSize({width, height});
        await page.evaluate(() => window.scrollTo(0, 0));
        if (action) await action.scrollIntoViewIfNeeded();
        await page.screenshot({path: path.join(screenshots, label + '-' + name + '.png'), animations: 'disabled'});
      }
    } finally {
      await page.setViewportSize(original);
      await page.evaluate(() => window.scrollTo(0, 0));
    }
  }

  async function groupListStatus(completed) {
    for (const list of ['summaries/', 'summaries/deals/']) {
      await page.goto(zs + '/' + list);
      const statusInRow = id => page.locator('tr[data-href^="/summaries/' + id + '/"] .policy-list-status');
      assert.match(await statusInRow(4).innerText(), new RegExp(completed + ' из 18'));
      assert.match(await statusInRow(1).innerText(), /QA-NEW/);
      if (completed === 15) await capture(list.includes('deals') ? 'zs-deals-list' : 'zs-summaries-list', null, true);
    }
  }

  async function checkSidebar(url, parent, image) {
    await page.goto(url);
    const card = page.locator(parent + ' > .policy-handoff');
    assert.equal(await card.count(), 1);
    const box = await card.boundingBox();
    assert.ok(box.x > page.viewportSize().width / 2, 'expected policy block in the desktop right column');
    await capture(image, card, true);
  }

  async function assignGroupContracts() {
    const plan = page.locator('form').filter({has: page.locator('button[value=plan]')});
    for (const [from, to, index] of [[1, 5, 1], [6, 10, 2], [11, 15, 3], [16, 18, 4]]) {
      const section = plan.locator('xpath=ancestor::details[not(@open)][1]');
      if (await section.count()) await section.locator('summary').first().click();
      await plan.locator('[name=range_start]').fill(String(from));
      await plan.locator('[name=range_end]').fill(String(to));
      await plan.locator('[name=group_dfa]').fill('ДЕМО-ДФА-' + index);
      await plan.getByRole('button', {name: /сохранить|добавить|подтвердить|назначить/i}).click();
      await plan.waitFor({state: 'attached'});
    }
  }

  async function checkFormWidgets() {
    const client = page.locator('.flow-field').filter({has: page.locator('#id_client')});
    await client.locator('.select2-selection').click();
    await page.locator('.select2-container--open .select2-search__field').fill('Тестовый');
    await page.getByRole('option', {name: /Тестовый лизингополучатель/}).click();
    const inline = page.locator('#payment_schedule-group');
    const count = inline.locator('[name=payment_schedule-TOTAL_FORMS]');
    const initial = Number(await count.inputValue());
    await inline.locator('.add-row a').click();
    assert.equal(Number(await count.inputValue()), initial + 1);
    await inline.locator('#payment_schedule-' + initial + ' .inline-deletelink').click();
    assert.equal(Number(await count.inputValue()), initial);
    const toggle = page.locator('[data-flow-extra-payments]');
    await toggle.check();
    assert.equal(await inline.locator('[name=payment_schedule-0-paid_date]').isVisible(), true);
    await toggle.uncheck();
    assert.equal(await inline.locator('[name=payment_schedule-0-paid_date]').isVisible(), false);
    const viewport = page.viewportSize();
    await page.setViewportSize({width: 1440, height: 900});
    const table = inline.locator('.tabular');
    assert.ok(await table.evaluate(el => el.scrollWidth <= el.clientWidth + 1),
              'basic payment columns should fit on a desktop');
    await capture('polis-payment-schedule', table, true);
    await page.setViewportSize(viewport);
  }

  async function checkDelayedRate() {
    // A manager can correct premiums while the initial rate request is still in flight.
    let release;
    const ready = new Promise(resolve => { release = resolve; });
    const endpoint = polis + '/insurers/api/commission-rate/**';
    const handle = async route => {
      await ready;
      await route.continue();
    };
    const payment = (i, name) => page.locator('[name=payment_schedule-' + i + '-' + name + ']');
    await page.route(endpoint, handle);
    try {
      await Promise.all([page.waitForRequest(endpoint), page.reload({waitUntil: 'domcontentloaded'})]);
      await payment(0, 'amount').fill('100');
      await payment(1, 'amount').fill('200');
      await payment(1, 'kv_rub').fill('7.77');
      release();
      await page.waitForLoadState('networkidle');
      const automatic = await payment(0, 'kv_rub').inputValue();
      assert.ok(automatic === '' || Number(automatic) === 10, 'changed premium must not retain its earlier commission');
      assert.equal(Number(await payment(1, 'kv_rub').inputValue()), 7.77, 'preserve the explicit commission');
    } finally {
      release();
      await page.unroute(endpoint, handle);
    }
    await page.reload();
  }

  async function finishGroup() {
    const groupUrl = zs + '/summaries/4/deal-summary/';
    await groupListStatus(15);
    await checkSidebar(zs + '/summaries/4/', '.sd-page .col-lg-4 .sd-aside', 'zs-summary-sidebar');
    await checkSidebar(groupUrl, '.ds-page .col-lg-4', 'zs-deal-sidebar');
    const linked = page.locator('.policy-handoff details');
    const status = page.locator('.policy-handoff__status');
    assert.match(await status.innerText(), /Оформлено 15 из 18\s*·\s*Осталось 3/);
    assert.equal(await linked.locator('a').count(), 15);
    assert.equal(await linked.evaluate(el => el.open), false);
    await capture('zs-15-of-18');
    await page.getByRole('button', {name: 'Оформить оставшиеся 3', exact: true}).click();
    await assignGroupContracts();
    await capture('polis-group-review', null, true);
    const position = page.locator('select[name=slot]');
    if (await position.count()) await position.selectOption('16');
    await page.getByRole('button', {name: /Создать отдельный полис|Оформить объект.*16/}).click();

    const next = page.getByRole('button', {name: 'Сохранить и оформить следующий', exact: true}).first();
    const saveCurrent = page.getByRole('button', {name: 'Сохранить полис и связать со сводом'}).first();
    for (const slot of [16, 17, 18]) {
      const label = new RegExp('объект\\s*(?:№\\s*)?' + slot + '\\s+из\\s+18', 'i');
      await page.getByRole('heading', {name: label}).waitFor();
      assert.ok(new URL(page.url()).pathname.startsWith('/policies/from-zs/'), 'use the manager portal');
      const source = page.locator('#flow-policy-source');
      assert.match(await source.innerText(), /Абсолют/);
      assert.equal(await source.locator('a').first().getAttribute('href'), zs + '/summaries/4/');
      assert.equal(await page.locator('#id_dfa_number').inputValue(), 'ДЕМО-ДФА-4');
      for (const field of ['policy_number', 'vin_number']) {
        assert.equal(await page.locator('#id_' + field).inputValue(), '', 'fresh field ' + field);
      }
      assert.doesNotMatch(await page.locator('#id_property_description').inputValue(), /Позиция ДЕМО/);
      const last = slot === 18;
      assert.equal(await next.isVisible(), !last);
      const number = 'ДЕМО-26-' + String(slot).padStart(4, '0');
      const sample = page.locator('[name=_flow_template]');
      assert.equal(await sample.isChecked(), false, 'template use requires an explicit decision');
      if (slot === 16) {
        assert.equal(await page.locator('#id_start_date').inputValue(), '');
        assert.equal(await page.locator('[name=payment_schedule-0-amount]').inputValue(), '');
        await capture('polis-group-form');
        await fillRequisites(number);
        for (const [index, amount] of [1516, 1516, 2116].entries()) {
          await page.locator('[name=payment_schedule-' + index + '-amount]').fill(String(amount));
          await page.locator('[name=payment_schedule-' + index + '-insurance_sum]').fill(index < 2 ? '300000' : '250000');
        }
        const extra = page.locator('[data-flow-extra-payments]');
        await extra.check();
        await page.locator('[name=payment_schedule-0-paid_date]').fill('01.01.' + (new Date().getFullYear() + 1));
        await extra.uncheck();
        await sample.check();
      } else {
        const firstYear = new Date().getFullYear() + 1;
        assert.equal(await page.locator('#id_start_date').inputValue(), '01.01.' + firstYear);
        assert.equal(await page.locator('#id_end_date').inputValue(), '31.12.' + (firstYear + 1));
        for (const [i, amount] of [1516, 1516, 2116].entries()) {
          assert.equal(Number(await page.locator('[name=payment_schedule-' + i + '-amount]').inputValue()), amount);
        }
        await page.locator('#id_policy_number').fill(number);
        if (slot === 17) await capture('polis-next-17');
        if (last) await page.locator('[name=payment_schedule-2-amount]').fill('2199');
      }
      await page.locator('#id_vin_number').fill('XTEST' + String(slot).padStart(12, '0'));
      await page.locator('#id_property_description').fill('Позиция ДЕМО ' + slot);
      if (slot === 16) {
        await capture('polis-save-16', next);
        // The ordinary Django form must keep this slot and its entered data on a validation error.
        await page.locator('[name=payment_schedule-0-amount]').fill('-1');
        await next.click();
        await page.locator('.errorlist').first().waitFor();
        assert.match(await page.locator('h1').innerText(), label);
        assert.equal(await page.locator('#id_policy_number').inputValue(), number);
        await page.locator('[name=payment_schedule-0-amount]').fill('1516');
        await page.locator('[name=payment_schedule-0-kv_rub]').fill('77.13');
        await sample.check();
      }
      const draftUrl = page.url();
      const submit = page.waitForRequest(request => request.url() === draftUrl && request.method() === 'POST');
      await (last ? saveCurrent : next).click();
      let submitted = await submit;
      if (slot !== 16 || page.url() === draftUrl) {
        const confirm = page.getByRole('button', {name: 'Создать отдельный полис с введёнными данными'});
        await confirm.waitFor();
        assert.equal(await page.getByRole('link', {name: 'QA-UNRELATED', exact: true}).count(), 1);
        assert.equal(await page.getByRole('link', {name: /^ДЕМО-26-/}).count(), 0,
                     'other positions of the same group must not be offered for linking');
        [submitted] = await Promise.all([
          page.waitForRequest(request => request.url() === draftUrl && request.method() === 'POST'),
          confirm.click(),
        ]);
      }
      await page.waitForURL(url => url.href !== draftUrl);
      if (slot === 16) {
        // A retried ordinary form POST must return to the same next draft without another write.
        const repeated = await page.request.post(draftUrl, {
          data: submitted.postDataBuffer(), maxRedirects: 0,
          headers: {'Content-Type': submitted.headers()['content-type'], Origin: polis, Referer: draftUrl},
        });
        assert.equal(repeated.status(), 302);
        assert.equal(new URL(repeated.headers().location, polis).href, page.url());
      }
    }
    await page.waitForURL(url => /^\/policies\/\d+\/$/.test(url.pathname));
    assert.match(await page.locator('h1').innerText(), /ДЕМО-26-0018/);
    await page.goto(groupUrl);
    assert.equal((await status.innerText()).trim(), 'Оформлено 18 из 18');
    assert.equal(await linked.locator('a').count(), 18);
    assert.equal(await page.locator('.policy-handoff form').count(), 0);
    await capture('zs-completed');
    await linked.locator('summary').click();
    await page.getByRole('link', {name: /ДЕМО-26-0018/}).click();
    assert.match(await page.locator('h1').innerText(), /ДЕМО-26-0018/);
    await groupListStatus(18);
  }

  try {
    await page.goto(zs + '/login/');
    await login(page, 'zs-operator', process.env.FLOW_QA_ZS_PASSWORD);
    await start(1);
    await page.waitForURL(url => url.origin === polis && url.pathname.endsWith('/login/'));
    await login(page, 'polis-editor', process.env.FLOW_QA_POLIS_PASSWORD);
    await page.waitForSelector('#id_policy_number');
    const formUrl = page.url();
    await capture('polis-create', null, true);
    await checkFormWidgets();
    await checkDelayedRate();
    const created = await save('QA-NEW');
    await verifyRoundtrip(1, 'QA-NEW', created);
    console.log('Browser PASS: new policy, separate login, two annual offers and reverse links');

    await page.goto(zs + '/summaries/deals/');
    await page.locator('tr[data-href="/summaries/2/deal-summary/"]').getByRole('button', {
      name: 'Проверить по ДФА', exact: true,
    }).click();
    await page.getByRole('radio', {name: 'Выбрать полис QA-OLD'}).waitFor();
    await checkReader(page.url(), created, formUrl);
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
    await finishGroup();
    console.log('Browser PASS: three real split policies, invalid form, DFA match, next unit and completed group');
  } catch (error) {
    console.error('Location:', new URL(page.url()).pathname);
    console.error('Page feedback:', (await page.locator('h1, h2, .errorlist, .errornote, .alert, [role=alert]').allTextContents()).join(' | ').slice(0, 2000));
    throw error;
  } finally {
    await browser.close();
  }
}
run().catch(error => { console.error(error.message); process.exitCode = 1; });
