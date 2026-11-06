"""Controlling-TTY password transport uses synthetic child processes only."""
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import os
from pathlib import Path
import signal
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.recovery_age import AgeProcessError, run_age_with_password


CANARY = 'SYNTHETIC-AGE-SECRET-NEVER-LOG'
CHILD = '''import os,sys,termios,time
from pathlib import Path
mode=sys.argv[1]
assert os.isatty(0)
assert os.tcgetpgrp(0)==os.getpgrp()
with open('/dev/tty','rb',buffering=0): pass
assert not(termios.tcgetattr(0)[3] & (termios.ECHO|termios.ECHONL))
assert not(termios.tcgetattr(0)[3] & termios.ICANON)
assert 'SYNTHETIC-AGE-SECRET-NEVER-LOG' not in '\\n'.join(sys.argv)
assert 'SYNTHETIC-AGE-SECRET-NEVER-LOG' not in '\\n'.join(os.environ.values())
if mode=='hang':
    Path(sys.argv[2]).write_text(str(os.getpid()))
    time.sleep(20)
if mode=='loud':
    os.write(1,b'X'*70000)
    raise SystemExit(0)
if mode=='no_prompt': raise SystemExit(0)
if mode=='enable_echo':
    settings=termios.tcgetattr(0);settings[3]|=termios.ECHO|termios.ICANON
    termios.tcsetattr(0,termios.TCSANOW,settings)
baseline=termios.tcgetattr(0)
prompts=['Enter passphrase:']
if mode=='encrypt': prompts.append('Confirm passphrase:')
for prompt in prompts:
    os.write(2,prompt.encode())
    if mode!='enable_echo':
        # Model native ReadPassword: prompt first, then a flushing ioctl.
        # Input written before this delayed transition would be discarded.
        time.sleep(0.05)
        reading=termios.tcgetattr(0);reading[3]|=termios.ICANON|termios.ISIG
        termios.tcsetattr(0,termios.TCSAFLUSH,reading)
    password=sys.stdin.readline().rstrip('\\n')
    termios.tcsetattr(0,termios.TCSAFLUSH,baseline)
    wanted='passphrase' if mode.startswith('prompt_word') else 'SYNTHETIC-AGE-SECRET-NEVER-LOG'
    if password!=wanted:
        os.write(2,b'private diagnostic SYNTHETIC-AGE-SECRET-NEVER-LOG')
        raise SystemExit(2)
    if mode in ('echo_secret','prompt_word_echo'): os.write(1,password.encode())
'''


class RecoveryAgeTests(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='recovery-age-test-')
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.child = self.root / 'synthetic_child.py'
        self.child.write_text(CHILD)

    def run_child(self, mode, password=CANARY, **options):
        return run_age_with_password([sys.executable, str(self.child), mode], password,
                                     expected_prompts=2 if mode == 'encrypt' else 1,
                                     timeout=options.pop('timeout', 5), **options)

    def test_encrypt_and_decrypt_have_private_controlling_tty_without_argv_or_env_secret(self):
        for mode in ('encrypt', 'decrypt'):
            with self.subTest(mode=mode):
                self.assertIsNone(self.run_child(mode))

    def test_password_matching_fixed_prompt_text_is_not_mistaken_for_echo(self):
        self.assertIsNone(self.run_child('prompt_word', password='passphrase'))

    def test_actual_password_echo_is_rejected_without_returning_terminal_output(self):
        for mode, password in [('echo_secret', CANARY), ('prompt_word_echo', 'passphrase')]:
            with self.subTest(mode=mode):
                out, err = StringIO(), StringIO()
                with redirect_stdout(out), redirect_stderr(err), self.assertRaises(AgeProcessError) as error:
                    self.run_child(mode, password)
                self.assertNotIn(CANARY, str(error.exception) + out.getvalue() + err.getvalue())
                self.assertEqual(out.getvalue() + err.getvalue(), '')

    def test_partial_terminal_writes_deliver_the_complete_password(self):
        original = os.write
        with patch('scripts.recovery_age.os.write', side_effect=lambda fd, data: original(fd, data[:3])) as write:
            self.assertIsNone(self.run_child('decrypt'))
        self.assertGreater(write.call_count, 1)

    def test_wrong_password_diagnostics_never_escape(self):
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err), self.assertRaises(AgeProcessError) as error:
            self.run_child('decrypt', password='SYNTHETIC-WRONG-PASSWORD')
        self.assertNotIn(CANARY, str(error.exception) + out.getvalue() + err.getvalue())

    def test_echo_enabled_before_prompt_is_rejected_before_password_is_sent(self):
        with self.assertRaisesRegex(AgeProcessError, 'echo must be disabled'):
            self.run_child('enable_echo')

    def test_timeout_kills_process_group_and_reaps_child(self):
        pid_file = self.root / 'child.pid'
        with patch('scripts.recovery_age.os.killpg', wraps=os.killpg) as kill:
            with self.assertRaisesRegex(AgeProcessError, 'timed out'):
                run_age_with_password([sys.executable, str(self.child), 'hang', str(pid_file)],
                                      CANARY, expected_prompts=1, timeout=1)
        pid = int(pid_file.read_text())
        kill.assert_called_once_with(pid, signal.SIGKILL)
        with self.assertRaises(ChildProcessError):
            os.waitpid(pid, os.WNOHANG)

    def test_missing_prompts_or_excessive_output_fail_closed(self):
        for mode in ('no_prompt', 'loud'):
            with self.subTest(mode=mode), self.assertRaises(AgeProcessError):
                self.run_child(mode)

    def test_invalid_password_or_prompt_contract_does_not_start_child(self):
        cases = [('', 1), ('secret\nsecond line', 1), ('secret\r', 1), ('secret\x00', 1),
                 (CANARY, 0), (CANARY, 3)]
        with patch('scripts.recovery_age.pty.fork') as fork:
            for password, prompts in cases:
                with self.subTest(prompts=prompts), self.assertRaises(AgeProcessError):
                    run_age_with_password([sys.executable], password, prompts)
        fork.assert_not_called()
