"""Логотипы страховых компаний для интерфейса.

Файлы лежат в static/img/insurers/<logo_code>.png, код логотипа хранится в InsuranceCompany.logo_code.
Словарь «название → URL логотипа» кэшируется в процессе на несколько минут и сбрасывается при
сохранении компании; у компании без логотипа интерфейс показывает первую букву названия.
"""
import logging
import time

from django.templatetags.static import static

logger = logging.getLogger(__name__)

CACHE_SECONDS = 300
_cache = {'loaded_at': 0.0, 'urls': None}


def logo_urls():
    """{название компании: URL логотипа} для компаний, у которых задан logo_code."""
    now = time.monotonic()
    if _cache['urls'] is None or now - _cache['loaded_at'] > CACHE_SECONDS:
        from summaries.models import InsuranceCompany

        urls = {}
        for name, display_name, code in InsuranceCompany.objects.exclude(logo_code='').values_list(
            'name', 'display_name', 'logo_code'
        ):
            try:
                url = static(f'img/insurers/{code}.png')
            except ValueError:  # файла нет в манифесте статики — показываем букву
                logger.warning('Insurer logo %s.png not found for %s', code, name)
                continue
            urls[name] = url
            if display_name:
                urls.setdefault(display_name, url)
        _cache.update(loaded_at=now, urls=urls)
    return _cache['urls']


def clear_cache():
    _cache.update(loaded_at=0.0, urls=None)


def monogram(name):
    """Первая буква названия для заглушки вместо логотипа."""
    return next((char.upper() for char in str(name) if char.isalnum()), '?')
