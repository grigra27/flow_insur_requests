"""«Новое / б/у» свободным текстом → структурное состояние объекта (`InsuranceRequest.condition`).

Используется парсером V2 (текст из бланка) и командой migrate_legacy_object_fields (архив asset_status).
"""
from __future__ import annotations

import re

NEW_WORDS = {'новое', 'новый', 'новая', 'new'}
USED_WORDS = {'бу', 'used', 'подержанное'}


def condition_from_asset_status(value) -> str | None:
    """«новое», «новое новое» → new; «б/у», «БУ», «б.у.» → used; иначе None."""
    words = set(re.sub(r'[/.\-]', '', (value or '').lower()).split())
    if not words:
        return None
    if words <= NEW_WORDS:
        return 'new'
    if words <= USED_WORDS:
        return 'used'
    return None
