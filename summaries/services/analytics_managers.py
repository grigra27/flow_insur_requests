"""Сервис аналитики по сотрудникам (Django-юзерам, загружающим заявки).

Этот модуль содержит скелеты функций, которые будут наполняться по фазам
из docs/_internal/employee_analytics_plan.md. На Phase 0 это заглушки,
возвращающие минимально валидные структуры, чтобы шаблоны и тесты могли
рендериться/проходить.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone


# Дефолтный период обзора, дней (см. план §«Зафиксированные решения», п.8).
DEFAULT_PERIOD_DAYS = 365

# Веса composite quality-score (см. план §«Зафиксированные решения», п.4).
QUALITY_SCORE_WEIGHTS: dict[str, float] = {
    'completeness': 0.40,
    'win_rate': 0.30,
    'speed': 0.20,
    'volume': 0.10,
}


@dataclass
class ManagerAnalyticsFilters:
    """Разобранные GET-параметры страницы /analytics/managers/."""

    period_days: int = DEFAULT_PERIOD_DAYS
    start_date: datetime | None = None
    end_date: datetime | None = None
    user_ids: list[int] = field(default_factory=list)
    branch: str | None = None
    insurance_type: str | None = None
    deal_status: str | None = None
    include_unassigned: bool = True
    only_active_users: bool = True
    errors: list[str] = field(default_factory=list)

    def resolved_window(self) -> tuple[datetime, datetime]:
        """Возвращает (start, end) с учётом дефолтного периода."""
        end = self.end_date or timezone.now()
        if self.start_date:
            start = self.start_date
        else:
            start = end - timedelta(days=self.period_days)
        return start, end


def parse_filters(get_params) -> ManagerAnalyticsFilters:
    """Разбирает request.GET в ManagerAnalyticsFilters.

    Phase 0: упрощённый парсер, поддерживает только period_days.
    Расширяется в Phase 1.
    """
    filters = ManagerAnalyticsFilters()
    raw_period = get_params.get('period_days')
    if raw_period:
        try:
            filters.period_days = max(1, int(raw_period))
        except (TypeError, ValueError):
            filters.errors.append('Некорректный параметр period_days')
    return filters


def build_overview_payload(filters: ManagerAnalyticsFilters) -> dict[str, Any]:
    """Данные для /analytics/managers/ (обзор всех сотрудников).

    Phase 0: пустой payload-плейсхолдер. Реальные агрегации появятся в Phase 1.
    """
    start, end = filters.resolved_window()
    return {
        'filters': filters,
        'window': {'start': start, 'end': end},
        'managers': [],
        'team': {},
        'kpi': {},
        'phase': 0,
    }


def build_manager_profile_payload(user_id: int, filters: ManagerAnalyticsFilters) -> dict[str, Any]:
    """Данные для /analytics/managers/<user_id>/ (досье).

    Phase 0: пустой payload. Заполняется в Phase 4.
    """
    return {
        'filters': filters,
        'user_id': user_id,
        'profile': None,
        'kpi': {},
        'activity': [],
        'phase': 0,
    }


def build_compare_payload(user_ids: list[int], filters: ManagerAnalyticsFilters) -> dict[str, Any]:
    """Данные для /analytics/managers/compare/.

    Phase 0: пустой payload. Заполняется в Phase 3.
    """
    return {
        'filters': filters,
        'user_ids': user_ids,
        'managers': [],
        'phase': 0,
    }


def build_leaderboard_payload(filters: ManagerAnalyticsFilters) -> dict[str, Any]:
    """Данные для admin-only леденборда.

    Phase 0: пустой payload. Заполняется в Phase 3.
    """
    return {
        'filters': filters,
        'rows': [],
        'phase': 0,
    }


def build_alerts(filters: ManagerAnalyticsFilters) -> list[dict[str, Any]]:
    """Список алертов для шапки обзора.

    Phase 0: пустой список. Заполняется в Phase 1–2.
    """
    return []
