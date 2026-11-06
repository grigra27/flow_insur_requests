"""Encrypted recovery transport never sends plaintext or leaks signed VK URLs."""
from io import StringIO
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
import zipfile

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, override_settings

from backup.recovery_vk import atomic_json, sha256_file, validate_archive

CANARY = 'SECRET_CANARY_NEVER_LOG'
PAYLOAD = (b'age-encryption.org/v1\n-> X25519 ' + b'A' * 43 + b'\n' + b'B' * 43
           + b'\n--- ' + b'C' * 43 + b'\n' + b'\x00' * 16 + b'X' * 48)


def passphrase_payload(factor=18, salt=b'A' * 22, body=b'B' * 42 + b'A'):
    return (b'age-encryption.org/v1\n-> scrypt ' + salt + b' ' + str(factor).encode('ascii')
            + b'\n' + body + b'\n--- ' + b'C' * 43 + b'\n' + b'\x00' * 16 + b'X' * 48)


@override_settings(VK_BACKUP_TOKEN=CANARY, VK_BACKUP_PEER_ID='12345', VK_API_VERSION='5.199')
class RecoveryVKTests(SimpleTestCase):
    def setUp(self):
        directory = TemporaryDirectory(prefix='recovery-vk-test-')
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.archive = self.directory / 'recovery.zip'
        self.receipt = self.directory / 'recovery.sent.json'
        self.output = StringIO()
        self.archive_fixture()
        self.log_output = StringIO()
        handler = logging.StreamHandler(self.log_output)
        logger = logging.getLogger('backup.send_backup_to_vk')
        previous_level = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        self.addCleanup(logger.removeHandler, handler)
        self.addCleanup(logger.setLevel, previous_level)
        network = patch('backup.recovery_vk.requests.post', side_effect=AssertionError('Unexpected network'))
        self.post = network.start()
        self.addCleanup(network.stop)

    def archive_fixture(self, payload=PAYLOAD, extra=None):
        with zipfile.ZipFile(self.archive, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('payload.tar.age', payload)
            archive.writestr('README.txt', 'Owner key is kept separately.')
            if extra:
                archive.writestr(extra, 'must never be uploaded')

    def response(self, payload=None, status=200):
        response = MagicMock()
        response.status_code = status
        response.json.return_value = payload
        if status >= 400:
            response.raise_for_status.side_effect = requests.HTTPError(
                'https://private.upload/?token=' + CANARY, response=response
            )
        return response

    def successful_posts(self):
        return [self.response({'response': {'upload_url': 'https://private.upload/upload.php?sig=' + CANARY}}),
                self.response({'file': CANARY}),
                self.response({'response': {'type': 'doc', 'doc': {'id': 99, 'owner_id': -7, 'access_key': CANARY}}}),
                self.response({'response': 42})]

    def send(self, **options):
        defaults = dict(archive=str(self.archive), expected_sha256=sha256_file(self.archive),
                        receipt_file=str(self.receipt), no_notify=True, stdout=self.output)
        defaults.update(options)
        return call_command('send_recovery_to_vk', **defaults)

    def saved_receipt(self):
        self.post.side_effect = self.successful_posts()
        self.send()
        return json.loads(self.receipt.read_text())

    def test_success_receipt_is_private_and_stdout_omits_private_metadata(self):
        receipt = self.saved_receipt()
        self.assertEqual(receipt['sha256'], sha256_file(self.archive))
        self.assertEqual(receipt['size'], self.archive.stat().st_size)
        self.assertEqual(receipt['document']['access_key'], CANARY)
        self.assertEqual(receipt['message_id'], 42)
        self.assertEqual(self.receipt.stat().st_mode & 0o777, 0o600)
        self.assertFalse(list(self.directory.glob('*.part')))
        safe = json.loads(self.output.getvalue())
        self.assertEqual(safe['status'], 'sent')
        self.assertNotIn(CANARY, self.output.getvalue() + self.log_output.getvalue())
        self.assertNotIn('https://', self.output.getvalue())
        self.assertNotIn('document', safe)
        message = self.post.call_args.kwargs['data']['message']
        self.assertIn('база данных, документы и настройки', message)
        self.assertIn('отдельный ключ владельца', message)

    def test_passphrase_archive_send_and_download_need_no_password_in_web(self):
        self.archive_fixture(payload=passphrase_payload())
        receipt = self.saved_receipt()
        self.assertEqual(receipt['sha256'], sha256_file(self.archive))
        message = self.post.call_args.kwargs['data']['message']
        self.assertIn('пароль архива', message)
        self.assertIn('Отдельный ключ не нужен', message)
        self.assertNotIn('отдельный ключ владельца', message)
        target, result, unused = self.download()
        self.assertEqual(target.read_bytes(), self.archive.read_bytes())
        self.assertEqual(result['status'], 'downloaded')
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertNotIn(CANARY, self.output.getvalue() + self.log_output.getvalue())

    def test_scrypt_work_factor_accepts_only_the_bounded_supported_range(self):
        for factor in (1, 18, 20):
            with self.subTest(factor=factor):
                self.archive_fixture(payload=passphrase_payload(factor))
                path, size, digest = validate_archive(self.archive, sha256_file(self.archive))
                self.assertEqual(path, self.archive)
                self.assertEqual(size, self.archive.stat().st_size)
                self.assertEqual(digest, sha256_file(self.archive))
        self.post.assert_not_called()

    def test_malformed_or_mixed_scrypt_recipients_fail_before_network(self):
        scrypt = passphrase_payload()
        stanza = scrypt.split(b'\n', 1)[1].split(b'--- ', 1)[0]
        cases = {str(factor): passphrase_payload(factor) for factor in (0, 21, 24, 99, -1, '018')}
        cases.update({
            'short_salt': passphrase_payload(salt=b'A' * 21),
            'padded_salt': passphrase_payload(salt=b'A' * 22 + b'=='),
            'noncanonical_salt': passphrase_payload(salt=b'A' * 21 + b'B'),
            'short_wrapped_key': passphrase_payload(body=b'A' * 42),
            'noncanonical_wrapped_key': passphrase_payload(body=b'A' * 42 + b'B'),
            'multiple_scrypt': scrypt.replace(stanza, stanza + stanza, 1),
            'mixed_recipients': PAYLOAD.replace(b'--- ', stanza + b'--- ', 1),
        })
        for name, payload in cases.items():
            with self.subTest(case=name):
                self.archive_fixture(payload=payload)
                with self.assertRaises(CommandError):
                    self.send(no_notify=False)
        self.post.assert_not_called()
        self.assertFalse(self.receipt.exists())

    def test_existing_matching_receipt_prevents_another_network_delivery(self):
        self.saved_receipt()
        count = self.post.call_count
        returned = json.loads(self.send())
        self.assertEqual(returned['status'], 'already_sent')
        self.assertEqual(self.post.call_count, count)

    def test_random_id_is_stable_signed_32bit_across_delivery_retries(self):
        self.post.side_effect = self.successful_posts() + self.successful_posts()
        self.send()
        self.send(receipt_file=str(self.directory / 'second.sent.json'))
        identifiers = [call.kwargs['data']['random_id'] for call in self.post.call_args_list
                       if call.args[0].endswith('/messages.send')]
        self.assertEqual(identifiers[0], identifiers[1])
        self.assertTrue(-(2**31) <= identifiers[0] < 2**31)
        self.assertNotEqual(identifiers[0], 0)

    def test_plaintext_bad_age_extra_member_size_and_sha_fail_before_network(self):
        for case in ('plaintext', 'bad_age', 'extra', 'size', 'sha'):
            with self.subTest(case=case):
                self.archive_fixture()
                if case == 'plaintext':
                    self.archive.write_bytes(b'plain SQL and settings')
                if case == 'bad_age':
                    self.archive_fixture(payload=b'plaintext database backup')
                if case == 'extra':
                    self.archive_fixture(extra='settings.env')
                digest = sha256_file(self.archive)
                if case == 'sha':
                    digest = '0' * 64
                with patch('backup.recovery_vk.VK_FILE_SIZE_LIMIT', 1 if case == 'size' else 190 * 1024**2):
                    with self.assertRaises(CommandError):
                        self.send(expected_sha256=digest, no_notify=False)
        self.post.assert_not_called()
        self.assertFalse(self.receipt.exists())

    def test_missing_expected_sha_is_rejected_before_network(self):
        with self.assertRaises(CommandError):
            self.send(expected_sha256=None)
        self.post.assert_not_called()

    def test_crc_corruption_is_rejected_even_when_archive_sha_matches(self):
        data = bytearray(self.archive.read_bytes())
        offset = data.index(b'X' * 48)
        data[offset] ^= 1
        self.archive.write_bytes(data)
        with self.assertRaises(CommandError):
            self.send()
        self.post.assert_not_called()

    def test_retry_logger_never_receives_bearer_url_or_error_body(self):
        replies = self.successful_posts()
        self.post.side_effect = [replies[0], self.response({'error': CANARY}), *replies]
        with patch('backup.management.commands.send_backup_to_vk.time.sleep'):
            self.send(upload_attempts=2, retry_base_delay=0, retry_max_delay=0)
        self.assertEqual(self.post.call_count, 6)
        self.assertTrue(self.log_output.getvalue())
        self.assertNotIn(CANARY, self.log_output.getvalue() + self.output.getvalue())
        self.assertNotIn('private.upload', self.log_output.getvalue())

    def test_network_failure_sends_one_generic_alert_without_secret_diagnostics(self):
        self.post.side_effect = [self.successful_posts()[0], self.response(status=400),
                                 self.response({'response': 101})]
        with self.assertRaises(CommandError) as error:
            self.send(no_notify=False)
        self.assertEqual(self.post.call_count, 3)
        alerts = [call for call in self.post.call_args_list if call.args[0].endswith('/messages.send')]
        self.assertEqual(len(alerts), 1)
        self.assertNotIn('attachment', alerts[0].kwargs['data'])
        self.assertNotIn(CANARY, str(error.exception) + self.output.getvalue() + self.log_output.getvalue())
        self.assertFalse(self.receipt.exists())

    def test_upload_node_must_use_https_before_archive_transfer(self):
        self.post.side_effect = [self.response({'response': {'upload_url': 'http://unsafe.invalid/' + CANARY}})]
        with self.assertRaises(CommandError) as error:
            self.send(no_notify=True)
        self.assertEqual(self.post.call_count, 1)
        self.assertNotIn(CANARY, str(error.exception))

    def test_no_notify_suppresses_network_failure_alert(self):
        self.post.side_effect = requests.ConnectionError('secret signed URL ' + CANARY)
        with self.assertRaises(CommandError) as error:
            self.send(no_notify=True)
        self.assertEqual(self.post.call_count, 1)
        self.assertNotIn(CANARY, str(error.exception))

    def test_standalone_creation_failure_alert_needs_no_archive(self):
        self.post.side_effect = [self.response({'response': 101})]
        returned = call_command('send_recovery_to_vk', notify_failure=True,
                                failure_code='encryption', stdout=self.output)
        self.assertEqual(json.loads(returned)['status'], 'failure_notified')
        self.assertEqual(self.post.call_count, 1)
        self.assertNotIn('attachment', self.post.call_args.kwargs['data'])
        self.assertNotIn(CANARY, self.output.getvalue())

    def download(self, data=None, *, metadata=None, status=200):
        receipt = json.loads(self.receipt.read_text())
        document = dict(receipt['document'], size=receipt['size'], url='https://download.vk.invalid/?sig=' + CANARY)
        if metadata:
            document.update(metadata)
        self.post.side_effect = [self.response({'response': [document]})]
        response = self.response(status=status)
        response.headers = {}
        response.iter_content.return_value = [self.archive.read_bytes() if data is None else data]
        target = self.directory / 'downloaded.zip'
        with patch('backup.recovery_vk.requests.get', return_value=response) as get:
            result = call_command('download_recovery_from_vk', receipt_file=str(self.receipt),
                                  output_file=str(target), stdout=self.output)
        return target, json.loads(result), get

    def test_download_uses_authoritative_metadata_and_publishes_matching_bytes(self):
        self.saved_receipt()
        target, result, get = self.download()
        self.assertEqual(target.read_bytes(), self.archive.read_bytes())
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(result['status'], 'downloaded')
        self.assertEqual(get.call_args.kwargs['stream'], True)
        self.assertEqual(get.call_args.kwargs['allow_redirects'], False)
        self.assertTrue(self.post.call_args.args[0].endswith('/docs.getById'))
        self.assertNotIn(CANARY, self.output.getvalue())

    def test_truncated_corrupt_or_oversized_download_never_publishes_output(self):
        self.saved_receipt()
        original = self.archive.read_bytes()
        for data in (original[:-1], b'X' + original[1:], original + b'X'):
            with self.subTest(size=len(data)):
                with self.assertRaises(CommandError):
                    self.download(data)
                self.assertFalse((self.directory / 'downloaded.zip').exists())
                self.assertFalse(list(self.directory.glob('*.part')))

    def test_mismatching_document_metadata_cancels_before_download(self):
        self.saved_receipt()
        with patch('backup.recovery_vk.requests.get') as get:
            receipt = json.loads(self.receipt.read_text())
            self.post.side_effect = [self.response({'response': [dict(receipt['document'], size=1)]})]
            with self.assertRaises(CommandError):
                call_command('download_recovery_from_vk', receipt_file=str(self.receipt),
                             output_file=str(self.directory / 'downloaded.zip'), stdout=self.output)
        get.assert_not_called()

    def test_https_required_and_http_error_messages_are_sanitized(self):
        self.saved_receipt()
        for metadata, status in (({'url': 'http://not-secure.invalid/' + CANARY}, 200), ({}, 403)):
            with self.subTest(status=status):
                with self.assertRaises(CommandError) as error:
                    self.download(metadata=metadata, status=status)
                self.assertNotIn(CANARY, str(error.exception) + self.log_output.getvalue())
                self.assertFalse((self.directory / 'downloaded.zip').exists())

    def test_atomic_receipt_publication_failure_does_not_leave_partial_receipt(self):
        with patch('backup.recovery_vk.os.replace', side_effect=OSError(CANARY)):
            with self.assertRaises(OSError):
                atomic_json(self.receipt, {'private': CANARY})
        self.assertFalse(self.receipt.exists())
        self.assertFalse(list(self.directory.glob('*.part')))
