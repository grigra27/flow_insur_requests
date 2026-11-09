"""Run the two checkouts on loopback with fresh fixtures and exercise them in Chromium."""
import argparse
from contextlib import ExitStack
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


def run(polis):
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
                              JOIN auth_user u ON u.id=l.created_by_id ORDER BY l.source_id""").fetchall()
        assert links == [(1, 'QA-NEW', 'polis-editor'), (2, 'QA-OLD', 'polis-editor'),
                         (3, 'QA-SEPARATE', 'polis-editor')], links
        assert db.execute('SELECT count(*) FROM policies_policy').fetchone()[0] == 3
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
        print('3 source links, 3 policies (1 pre-existing), 3 expected payments per new policy. Reopening created no copies.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--polis', type=Path, default=ZS.parent / 'onlinepolis')
    run(parser.parse_args().polis.resolve())
