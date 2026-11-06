"""Moscow deadline input must retain UTC+3 when Django uses zoneinfo."""

from datetime import datetime, timedelta, timezone

from django.test import SimpleTestCase, override_settings

from .forms import DateTimeLocalWidget, InsuranceRequestForm, ParserV2PreviewForm


@override_settings(TIME_ZONE='UTC')
class DeadlineTimezoneTests(SimpleTestCase):
    def test_all_preview_formats_preserve_moscow_wall_time_and_utc_instant(self):
        form = ParserV2PreviewForm()
        for value, seconds in (
            ('2026-11-06T16:30', 0),
            ('2026-11-06 16:30:45', 45),
            ('06.11.2026 16:30', 0),
        ):
            with self.subTest(value=value):
                deadline = form._parse_response_deadline(value)
                self.assertEqual(deadline.utcoffset(), timedelta(hours=3))
                self.assertEqual(deadline.replace(tzinfo=None), datetime(2026, 11, 6, 16, 30, seconds))
                self.assertEqual(deadline.astimezone(timezone.utc),
                                 datetime(2026, 11, 6, 13, 30, seconds, tzinfo=timezone.utc))

    def test_empty_or_invalid_preview_deadlines_remain_unset(self):
        form = ParserV2PreviewForm()
        for value in (None, '', 'not a date', '2026-13-06T16:30'):
            with self.subTest(value=value):
                self.assertIsNone(form._parse_response_deadline(value))

    def test_edit_form_interprets_naive_deadline_as_moscow(self):
        form = InsuranceRequestForm()
        form.cleaned_data = {'response_deadline': datetime(2026, 11, 6, 16, 30)}
        deadline = form.clean_response_deadline()
        self.assertEqual(deadline.utcoffset(), timedelta(hours=3))
        self.assertEqual(deadline.astimezone(timezone.utc),
                         datetime(2026, 11, 6, 13, 30, tzinfo=timezone.utc))

    def test_edit_form_preserves_an_already_aware_instant(self):
        deadline = datetime(2026, 11, 6, 13, 30, tzinfo=timezone.utc)
        form = InsuranceRequestForm()
        form.cleaned_data = {'response_deadline': deadline}
        self.assertIs(form.clean_response_deadline(), deadline)

    def test_widget_displays_aware_deadline_in_moscow(self):
        deadline = datetime(2026, 11, 6, 13, 30, tzinfo=timezone.utc)
        self.assertEqual(DateTimeLocalWidget().format_value(deadline), '2026-11-06T16:30')
