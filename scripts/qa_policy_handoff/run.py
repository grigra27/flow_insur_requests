"""Run the two checkouts on loopback with fresh fixtures and exercise them in Chromium."""
import argparse
from contextlib import ExitStack
from datetime import date
import json
import os
from pathlib import Path
import secrets
import socket
import sqlite3
import subprocess
import tempfile
import time
from urllib.request import urlopen
from urllib.error import URLError

HERE = Path(__file__).resolve().parent
ZS = HERE.parents[1]
SETTINGS = """
from {module} import *
DATABASES = {{'default': {{'ENGINE': 'django.db.backends.sqlite3', 'NAME': {db!r}}}}}
STORAGES = {{'default': {{'BACKEND': 'django.core.files.storage.FileSystemStorage'}},
             'staticfiles': {{'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}}}
LOGGING = {{'version': 1, 'disable_existing_loggers': False, 'handlers': {{'quiet': {{'class': 'logging.NullHandler'}}}}, 'root': {{'handlers': ['quiet']}}}}
MEDIA_ROOT = {media!r}
PRODUCTION_CALENDAR_URL = ''
INTERNAL_IPS = []
"""

def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def manage(repo, env, *args, **kwargs):
    return subprocess.run([repo / 'venv/bin/python', 'manage.py', *args], cwd=repo,
                          env=env, text=True, check=True, **kwargs)


def stop(proc):
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def serve(repo, env, url, stack):
    port_number = url.rsplit(':', 1)[1]
    proc = subprocess.Popen([repo / 'venv/bin/python', 'manage.py', 'runserver',
                             f'127.0.0.1:{port_number}', '--noreload'],
                            cwd=repo, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stack.callback(stop, proc)
    health = '/healthz/' if repo == ZS else '/health/'
    for _ in range(200):
        try:
            with urlopen(url + health, timeout=1) as response:
                if response.status == 200:
                    return
        except URLError:
            pass
        if proc.poll() is not None:
            break
        time.sleep(.1)
    raise RuntimeError(f'Local server did not start: {url}')


def existing_snapshot(db):
    return (
        db.execute("SELECT * FROM policies_policy WHERE policy_number='QA-OLD'").fetchone(),
        db.execute("""SELECT p.* FROM policies_paymentschedule p JOIN policies_policy i ON i.id=p.policy_id
                      WHERE i.policy_number='QA-OLD' ORDER BY p.id""").fetchall(),
    )


def check_group(db):
    group = db.execute('SELECT mode, total FROM policies_flowpolicysource WHERE summary_id=4').fetchone()
    assert group == ('separate', 18), group
    plans = json.loads(db.execute(
        'SELECT groups FROM policies_flowpolicysource WHERE summary_id=4'
    ).fetchone()[0])
    assert [(plan['first_slot'], plan['last_slot'], plan['dfa']) for plan in plans] == [
        (1, 5, 'ДЕМО-ДФА-1'), (6, 10, 'ДЕМО-ДФА-2'), (11, 15, 'ДЕМО-ДФА-3'), (16, 18, 'ДЕМО-ДФА-4'),
    ]
    assert not any(plan.get('template') for plan in plans[:3])
    assert plans[3]['template_policy_number'] == 'ДЕМО-26-0016'
    rows = db.execute("""
        SELECT l.slot, p.policy_number, p.vin_number, p.dfa_number, u.username, l.created_from_summary
        FROM policies_flowpolicylink l JOIN policies_policy p ON p.id=l.policy_id
        JOIN auth_user u ON u.id=l.created_by_id WHERE l.source_id=4 ORDER BY l.slot
    """).fetchall()
    expected = [(slot, f'ДЕМО-26-{slot:04d}', f'XTEST{slot:012d}',
                 f'ДЕМО-ДФА-{(slot - 1) // 5 + 1}', 'polis-editor', True) for slot in range(1, 19)]
    assert rows == expected, rows
    first_year = date.today().year + 1
    expected_dates = [f'{first_year}-01-01', f'{first_year}-07-01', f'{first_year + 1}-01-01']
    for slot in range(16, 19):
        payments = db.execute("""
            SELECT s.year_number, s.installment_number, s.amount, s.insurance_sum,
                   s.due_date, s.kv_rub, s.paid_date, s.insurer_date
            FROM policies_paymentschedule s JOIN policies_flowpolicylink l ON l.policy_id=s.policy_id
            WHERE l.source_id=4 AND l.slot=? ORDER BY s.year_number, s.installment_number
        """, (slot,)).fetchall()
        assert [row[:4] for row in payments] == [
            (1, 1, 1516, 300000), (1, 2, 1516, 300000), (2, 1, 2199 if slot == 18 else 2116, 250000)
        ], payments
        assert [row[4] for row in payments] == expected_dates, payments
        for index, row in enumerate(payments):
            example = slot == 16 and index == 0
            assert round(row[5] * 100) == (7713 if example else round(row[2] * 10)), row
            assert row[6] == (expected_dates[0] if example else None) and row[7] is None, row


def run(polis, screenshots=None):
    with tempfile.TemporaryDirectory(prefix='flow-handoff-qa-') as directory, ExitStack() as stack:
        tmp = Path(directory)
        env = dict(os.environ, PYTHONPATH=str(tmp), DEBUG='True', SECRET_KEY=secrets.token_urlsafe(48),
                   FLOW_SERVICE_TOKEN=secrets.token_urlsafe(32), FLOW_HANDOFF_ENABLED='true',
                   FLOW_HANDOFF_GROUP='', FLOW_QA_ZS_PASSWORD=secrets.token_urlsafe(18),
                   FLOW_QA_POLIS_PASSWORD=secrets.token_urlsafe(18),
                   FLOW_ZS_BASE_URL=f'http://localhost:{port()}', FLOW_POLIS_BASE_URL=f'http://127.0.0.1:{port()}',
                   DB_NAME='', DB_ENGINE='django.db.backends.sqlite3', SENTRY_DSN='', TELEGRAM_ENABLED='false',
                   VK_ENABLED='false', PRODUCTION_CALENDAR_URL='', ENABLE_HTTPS='false',
                   SECURE_SSL_REDIRECT='false', ALLOWED_HOSTS='localhost,127.0.0.1', PYTHONDONTWRITEBYTECODE='1')
        if screenshots:
            screenshots.mkdir(parents=True, exist_ok=True)
            env['FLOW_QA_SCREENSHOTS'] = str(screenshots.resolve())
        for name, repo, module, url in [('zs', ZS, 'onlineservice.settings', env['FLOW_ZS_BASE_URL']),
                                        ('polis', polis, 'config.settings', env['FLOW_POLIS_BASE_URL'])]:
            settings = f'qa_{name}_settings'
            (tmp / (settings + '.py')).write_text(SETTINGS.format(
                module=module, db=str(tmp / (name+'.db')), media=str(tmp / 'media')))
            own_env = dict(env, DJANGO_SETTINGS_MODULE=settings)
            manage(repo, own_env, 'migrate', '--noinput', '--verbosity', '0', stdout=subprocess.DEVNULL)
            manage(repo, own_env, 'shell', '-c', (HERE / f'seed_{name}.py').read_text(), stdout=subprocess.DEVNULL)
            serve(repo, own_env, url, stack)

        db = sqlite3.connect(tmp / 'polis.db')
        stack.callback(db.close)
        original = existing_snapshot(db)
        subprocess.run(['node', HERE / 'browser.cjs'], env=env, check=True)
        assert original == existing_snapshot(db), 'Linking changed the original policy or its payments'
        links = db.execute("""SELECT l.source_id, p.policy_number, u.username FROM policies_flowpolicylink l
                              JOIN policies_policy p ON p.id=l.policy_id
                              JOIN auth_user u ON u.id=l.created_by_id WHERE l.source_id IN (1, 2, 3)
                              ORDER BY l.source_id""").fetchall()
        assert links == [(1, 'QA-NEW', 'polis-editor'), (2, 'QA-OLD', 'polis-editor'),
                         (3, 'QA-SEPARATE', 'polis-editor')], links
        check_group(db)
        # Three original scenarios, eighteen units, one unrelated policy, plus active and terminated examples.
        assert db.execute('SELECT count(*) FROM policies_policy').fetchone()[0] == 24
        for number in ('QA-NEW', 'QA-SEPARATE'):
            rows = db.execute("""SELECT year_number, installment_number, amount, insurance_sum, kv_rub,
                                 due_date, paid_date, insurer_date FROM policies_paymentschedule s
                                 JOIN policies_policy p ON p.id=s.policy_id
                                 WHERE p.policy_number=? ORDER BY year_number, installment_number""", (number,)).fetchall()
            first_commission = 1234 if number == 'QA-SEPARATE' else 50000
            assert [(y, i, round(a*100), sm, round(k*100)) for y, i, a, sm, k, *_ in rows] == [
                (1, 1, 500000, 1000000, first_commission), (1, 2, 500001, 1000000, 50000),
                (2, 1, 900000, 900000, 90000)], rows
            assert all(due and not paid and not act for *_, due, paid, act in rows), rows
        print('PASS: new policy, existing policy linked with every field/payment preserved, separate policy on same DFA.')
        print('PASS: 18 slots on four final DFAs; confirmed unit schedule reused, final correction isolated, no copies.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--polis', type=Path, default=ZS.parent / 'onlinepolis')
    parser.add_argument('--screenshots', type=Path, help='Save desktop and mobile views of the synthetic group')
    args = parser.parse_args()
    run(args.polis.resolve(), args.screenshots)
