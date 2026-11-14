"""Exercise policy-to-ZS linking across two fresh databases and real HTTP servers."""
import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import tempfile

from run import HERE, SETTINGS, ZS, manage, port, serve


ZS_FIXTURES = """
import json
from pathlib import Path
from summaries.services.policy_handoff import snapshot_and_options
for pk, dfa in [(1, 'ТС-12345/1'), (2, 'ТС-12345/2'), (3, 'ТС-54321'), (4, 'ТС-77777/1')]:
    row = InsuranceSummary.objects.select_related('request').get(pk=pk)
    row.request.dfa_number = dfa
    row.request.save(update_fields=['dfa_number'])
snapshot, _ = snapshot_and_options(InsuranceSummary.objects.select_related('request').get(pk=4))
Path(os.environ['FLOW_QA_MANIFEST']).write_text(json.dumps({'group_revision': snapshot['revision']}))
"""

POLIS_FIXTURES = """
import json
from pathlib import Path
manifest_path = Path(os.environ['FLOW_QA_MANIFEST'])
manifest = json.loads(manifest_path.read_text())
old = Policy.objects.get(policy_number='QA-OLD')
old.dfa_number = '12345-1'
old.save(update_fields=['dfa_number'])
group = FlowPolicySource.objects.get(pk=4)
group.groups = [{'first_slot': 16, 'last_slot': 18, 'dfa': '88888-1',
                 'revision': manifest['group_revision'], 'version': 'reverse-qa-range'}]
group.save(update_fields=['groups'])
targets = {'existing': old.pk}
for key, number, dfa in [('unit', 'QA-UNIT-16', '88888-1'),
                          ('conflict', 'QA-OCCUPIED', '88888-1'),
                          ('manual', 'QA-MANUAL', '99999')]:
    item = Policy.objects.create(**policy_fields, policy_number=number, dfa_number=dfa,
                                 property_description='Тестовый объект для привязки',
                                 vin_number='XTEST000000000016' if key == 'unit' else '')
    PaymentSchedule.objects.create(policy=item, year_number=1, installment_number=1,
        due_date=item.start_date, amount=2500, insurance_sum=300000, kv_rub=250)
    targets[key] = item.pk
manifest.update(targets)
manifest_path.write_text(json.dumps(manifest))
"""


def run(polis, screenshots=None):
    with tempfile.TemporaryDirectory(prefix='flow-reverse-qa-') as directory, ExitStack() as stack:
        tmp = Path(directory)
        env = dict(os.environ, PYTHONPATH=str(tmp), DEBUG='True',
                   SECRET_KEY=secrets.token_urlsafe(48), FLOW_SERVICE_TOKEN=secrets.token_urlsafe(32),
                   FLOW_HANDOFF_ENABLED='true', FLOW_HANDOFF_GROUP='',
                   FLOW_QA_ZS_PASSWORD=secrets.token_urlsafe(18),
                   FLOW_QA_POLIS_PASSWORD=secrets.token_urlsafe(18),
                   FLOW_ZS_BASE_URL=f'http://localhost:{port()}',
                   FLOW_POLIS_BASE_URL=f'http://127.0.0.1:{port()}',
                   FLOW_QA_MANIFEST=str(tmp / 'fixtures.json'),
                   DB_NAME='', DB_ENGINE='django.db.backends.sqlite3', SENTRY_DSN='',
                   TELEGRAM_ENABLED='false', VK_ENABLED='false', PRODUCTION_CALENDAR_URL='',
                   ENABLE_HTTPS='false', SECURE_SSL_REDIRECT='false',
                   ALLOWED_HOSTS='localhost,127.0.0.1', PYTHONDONTWRITEBYTECODE='1')
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            env['FLOW_QA_SCREENSHOTS'] = str(screenshots.resolve())
        for name, repo, module, url, seed in [
            ('zs', ZS, 'onlineservice.settings', env['FLOW_ZS_BASE_URL'], ZS_FIXTURES),
            ('polis', polis, 'config.settings', env['FLOW_POLIS_BASE_URL'], POLIS_FIXTURES),
        ]:
            settings = f'qa_{name}_settings'
            (tmp / (settings + '.py')).write_text(SETTINGS.format(
                module=module, db=str(tmp / (name + '.db')), media=str(tmp / 'media')))
            own_env = dict(env, DJANGO_SETTINGS_MODULE=settings)
            manage(repo, own_env, 'migrate', '--noinput', '--verbosity', '0', stdout=subprocess.DEVNULL)
            manage(repo, own_env, 'shell', '-c', (HERE / f'seed_{name}.py').read_text() + seed,
                   stdout=subprocess.DEVNULL)
            serve(repo, own_env, url, stack)

        db = sqlite3.connect(tmp / 'polis.db')
        stack.callback(db.close)
        before = {table: db.execute(f'SELECT * FROM {table} ORDER BY id').fetchall()
                  for table in ('policies_policy', 'policies_paymentschedule')}
        subprocess.run(['node', HERE / 'reverse_browser.cjs'], env=env, check=True)
        for table, rows in before.items():
            assert rows == db.execute(f'SELECT * FROM {table} ORDER BY id').fetchall(), table
        manifest = json.loads((tmp / 'fixtures.json').read_text())
        for source, slot, key in [(1, 0, 'existing'), (4, 16, 'unit'), (3, 0, 'manual')]:
            link = db.execute('''SELECT policy_id, created_from_summary, u.username
                FROM policies_flowpolicylink l JOIN auth_user u ON u.id=l.created_by_id
                WHERE source_id=? AND slot=?''', (source, slot)).fetchone()
            assert link == (manifest[key], False, 'polis-editor'), link
        assert db.execute('SELECT count(*) FROM policies_flowpolicylink WHERE source_id=4').fetchone() == (16,)
        assert db.execute('SELECT count(*) FROM policies_flowpolicylink WHERE policy_id=?',
                          (manifest['conflict'],)).fetchone() == (0,)
        print('PASS: prefix/separator match, 18-object group with final DFA, manual selection, occupied position, reader denial.')
        print('PASS: real service requests in both directions; every policy and payment field preserved.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--polis', type=Path, default=ZS.parent / 'onlinepolis')
    parser.add_argument('--screenshots', type=Path)
    args = parser.parse_args()
    run(args.polis.resolve(), args.screenshots)
