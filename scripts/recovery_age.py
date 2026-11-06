"""Run native age password prompts through a private controlling terminal."""
import errno
import math
import os
import pty
import re
import select
import signal
import termios
import time


class AgeProcessError(RuntimeError):
    """Static diagnostics only; never include terminal output or passwords."""


def _kill_and_reap(child):
    try:
        os.killpg(child, signal.SIGKILL)
    except ProcessLookupError:
        try:
            os.kill(child, signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            done, unused = os.waitpid(child, os.WNOHANG)
        except ChildProcessError:
            return
        if done:
            return
        time.sleep(0.01)
    raise AgeProcessError('Age process cleanup timed out.')


def _wait_for_password_reader(master, deadline):
    # age prints its prompt before x/term.ReadPassword changes the terminal.
    # Start noncanonical so ICANON becoming enabled acknowledges that ioctl,
    # including any input flush. Never guess readiness from a timing delay.
    while time.monotonic() < deadline:
        flags = termios.tcgetattr(master)[3]
        if flags & termios.ICANON:
            if flags & (termios.ECHO | termios.ECHONL):
                raise AgeProcessError('Age terminal echo must be disabled.')
            return
        time.sleep(min(0.005, max(0, deadline - time.monotonic())))
    raise AgeProcessError('Age password reader timed out.')


def run_age_with_password(arguments, password, expected_prompts, timeout=600):
    """Return None on success, or a safe error. INPUT and OUTPUT must be files.

    Encrypt: age -p -o OUTPUT INPUT, expected_prompts=2.
    Decrypt: age -d -o OUTPUT INPUT, expected_prompts=1.
    The password is never added to arguments or environment, and captured
    terminal output is never returned or logged. Compatible with Python 3.9.
    """
    try:
        if (not isinstance(password, str) or not password
                or any(char in password for char in ('\r', '\n', '\x00'))
                or expected_prompts not in (1, 2)
                or not math.isfinite(timeout) or timeout <= 0):
            raise AgeProcessError('Age process input is invalid.')
        secret = password.encode('utf-8')
        command = [os.fspath(argument) for argument in arguments]
        if not command or any(argument in (password, '-p' + password) for argument in command):
            raise AgeProcessError('Age process input is invalid.')
        prompts = [rb'Enter passphrase[^\r\n]*:']
        if expected_prompts == 2:
            prompts.append(rb'Confirm passphrase:')
        child, master = pty.fork()  # forkpty establishes a session and controlling TTY.
    except AgeProcessError:
        raise
    except Exception:
        raise AgeProcessError('Age process could not start.') from None
    if child == 0:
        try:
            attributes = termios.tcgetattr(0)
            attributes[0] &= ~termios.ICRNL
            attributes[3] &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG)
            attributes[6][termios.VMIN] = 1
            attributes[6][termios.VTIME] = 0
            termios.tcsetattr(0, termios.TCSANOW, attributes)
            os.umask(0o077)
            os.execve(command[0], command,
                      {'PATH': os.defpath, 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'})
        except BaseException:
            os._exit(127)
    status = None
    transcript, pending = bytearray(), b''
    prompt_spans = []
    sent, eof = 0, False
    deadline = time.monotonic() + timeout
    try:
        os.set_blocking(master, False)
        while time.monotonic() < deadline:
            if not eof and select.select([master], [], [], min(0.1, max(0, deadline-time.monotonic())))[0]:
                try:
                    block = os.read(master, 8192)
                except OSError as error:
                    if error.errno != errno.EIO:
                        raise
                    block = b''
                if not block:
                    eof = True
                else:
                    transcript.extend(block)
                    if len(transcript) > 65536:
                        raise AgeProcessError('Age terminal output exceeded its limit.')
                    pending += block
                    if sent < len(prompts):
                        match = re.search(prompts[sent], pending)
                        if match:
                            _wait_for_password_reader(master, deadline)
                            base = len(transcript) - len(pending)
                            prompt_spans.append((base + match.start(), base + match.end()))
                            line, written = secret + b'\n', 0
                            while written < len(line):
                                if time.monotonic() >= deadline:
                                    raise AgeProcessError('Age process timed out.')
                                if not select.select([], [master], [], min(0.1, max(0, deadline-time.monotonic())))[1]:
                                    continue
                                try:
                                    count = os.write(master, line[written:])
                                except BlockingIOError:
                                    continue
                                if count <= 0:
                                    raise AgeProcessError('Age password input failed.')
                                written += count
                            pending = pending[match.end():]
                            sent += 1
            done, child_status = os.waitpid(child, os.WNOHANG)
            if done:
                status = child_status
                # Drain already buffered output before checking for an echo.
                while select.select([master], [], [], 0)[0]:
                    try:
                        block = os.read(master, 8192)
                    except OSError as error:
                        if error.errno != errno.EIO:
                            raise
                        break
                    if not block:
                        break
                    transcript.extend(block)
                    if len(transcript) > 65536:
                        raise AgeProcessError('Age terminal output exceeded its limit.')
                break
            if eof:
                time.sleep(0.01)
        if status is None:
            raise AgeProcessError('Age process timed out.')
        # A legitimate password may itself be "passphrase". Fixed prompt text
        # is not an echo; inspect all other captured bytes, including final output.
        slices, end = [], 0
        for start, stop in prompt_spans:
            slices.append(transcript[end:start])
            end = stop
        slices.append(transcript[end:])
        if secret in b''.join(slices):
            raise AgeProcessError('Age terminal unexpectedly echoed the passphrase.')
        if os.waitstatus_to_exitcode(status) != 0:
            raise AgeProcessError('Age passphrase command failed.')
        if sent != expected_prompts:
            raise AgeProcessError('Age passphrase prompts were incomplete.')
    except AgeProcessError:
        raise
    except Exception:
        raise AgeProcessError('Age passphrase command failed.') from None
    finally:
        try:
            if status is None:
                _kill_and_reap(child)
        finally:
            os.close(master)
            transcript.clear()
