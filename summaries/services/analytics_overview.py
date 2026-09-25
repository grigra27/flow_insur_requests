"""Обзор аналитики: главные цифры за период и два графика.

Деньги и доли СК берутся из того же расчёта, что и страница «Страховые компании»
(`build_analytics_insurance_companies_payload`), чтобы цифры на двух страницах
совпадали. Заявки считаются по дате создания заявки, сделки (акцепты) — по дате
создания свода, как на странице СК.

docs/improvement_plans/analytics_redesign_2026_09.md, задача 1.6.
"""

from __future__ import annotations

from collections import Counter
from datetime import date
from decimal import Decimal
from typing import Callable, Dict, Optional

from insurance_requests.models import InsuranceRequest
from summaries.models import InsuranceSummary

from .analytics_insurance_companies import (
    OTHER_COMPANIES_LABEL,
    _month_label,
    _series_colors,
    build_analytics_insurance_companies_payload,
)

OPEN_SUMMARY_STATUSES = [
    ('collecting', 'сбор'),
    ('ready', 'готов'),
    ('sent', 'отправлен'),
]
SHARE_TOP_COMPANIES = 6


def build_overview_payload(
    *,
    start_date: Optional[date],
    end_date: Optional[date],
    price_row_builder: Callable,
) -> Dict:
    companies = build_analytics_insurance_companies_payload(
        start_date=start_date,
        end_date=end_date,
        price_row_builder=price_row_builder,
    )
    company_kpi = companies['kpi']
    winners = [row for row in companies['company_rows'] if row['is_winner']]

    requests = InsuranceRequest.objects.all()
    if start_date:
        requests = requests.filter(created_at__date__gte=start_date)
    if end_date:
        requests = requests.filter(created_at__date__lte=end_date)
    request_dates = list(requests.values_list('created_at', flat=True))

    accepted = InsuranceSummary.objects.filter(status='completed_accepted').exclude(
        selected_company__isnull=True
    ).exclude(selected_company='')
    if start_date:
        accepted = accepted.filter(created_at__date__gte=start_date)
    if end_date:
        accepted = accepted.filter(created_at__date__lte=end_date)
    accepted_dates = list(accepted.values_list('created_at', flat=True))

    requests_by_month = Counter(value.strftime('%Y-%m') for value in request_dates)
    accepted_by_month = Counter(value.strftime('%Y-%m') for value in accepted_dates)
    month_keys = sorted(set(requests_by_month) | set(accepted_by_month))

    # Открытые своды — текущее состояние, без периода: сколько сейчас в работе.
    open_counts = Counter(
        InsuranceSummary.objects.filter(
            status__in=[status for status, _ in OPEN_SUMMARY_STATUSES]
        ).values_list('status', flat=True)
    )

    top_share = winners[:SHARE_TOP_COMPANIES]
    other_deals = sum(row['deals'] for row in winners[SHARE_TOP_COMPANIES:])
    share_labels = [row['company_name'] for row in top_share]
    share_values = [row['deals'] for row in top_share]
    if other_deals:
        share_labels.append(OTHER_COMPANIES_LABEL)
        share_values.append(other_deals)
    share_colors = _series_colors(share_labels)

    total_deals = company_kpi['total_deals']
    return {
        'kpi': {
            'requests': len(request_dates),
            'deals': total_deals,
            'insured_sum_total': company_kpi['insured_sum_total'],
            'premium_total': company_kpi['premium_total'],
            'avg_tariff_pct': company_kpi['avg_tariff_pct'],
            'open_summaries': sum(open_counts.values()),
            'open_breakdown': [
                {'label': label, 'count': open_counts.get(status, 0)}
                for status, label in OPEN_SUMMARY_STATUSES
            ],
        },
        'top_companies': [
            {
                'company_name': row['company_name'],
                'deals': row['deals'],
                'deals_share_pct': row['deals_share_pct'],
                'insured_sum': row['insured_sum'],
            }
            for row in winners[:3]
        ],
        'charts': {
            'monthly': {
                'labels': [_month_label(month_key) for month_key in month_keys],
                'requests': [requests_by_month.get(month_key, 0) for month_key in month_keys],
                'deals': [accepted_by_month.get(month_key, 0) for month_key in month_keys],
            },
            'shares': {
                'labels': share_labels,
                'values': share_values,
                'percents': [
                    float(Decimal(value) / Decimal(total_deals) * 100) if total_deals else 0.0
                    for value in share_values
                ],
                'colors': [share_colors[label] for label in share_labels],
            },
        },
    }
