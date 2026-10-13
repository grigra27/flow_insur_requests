"""
Справочник филиалов: полные названия из бланков → короткие (используются парсером V2 и бейджами).

До 2026-10-13 здесь же жил загрузчик V1 (`ExcelReader`); он удалён в фазе D депрекейта
(docs/improvement_plans/backlog.md, п. 1). Новые полные названия филиалов добавляйте в BRANCH_MAPPING.
"""
import logging

logger = logging.getLogger(__name__)


# Маппинг полных названий филиалов на сокращенные
BRANCH_MAPPING = {
    "Казанский филиал": "Казань",
    "Нижегородский филиал": "Нижний Новгород",
    "Краснодарский филиал": "Краснодар",
    "Санкт-Петербург": "Санкт-Петербург",
    "Мурманский филиал": "Мурманск",
    "Псковский филиал": "Псков",
    "Челябинский филиал": "Челябинск",
    "Московский филиал № 2": "Москва",
    "Новгородский филиал": "Великий Новгород",
    "Архангельский филиал": "Архангельск",
    "Ставропольское обособленное подразделение": "Краснодар",
}

AVAILABLE_BRANCHES = frozenset(BRANCH_MAPPING.values())


def map_branch_name(full_branch_name: str) -> str:
    """
    Преобразует полное название филиала в сокращенное.
    
    Args:
        full_branch_name: Полное название филиала
        
    Returns:
        Сокращенное название филиала или оригинальное название, если маппинг не найден
    """
    if not full_branch_name or not isinstance(full_branch_name, str):
        return full_branch_name or "Филиал не указан"
    
    # Убираем лишние пробелы и приводим к единому виду
    normalized_name = full_branch_name.strip()
    
    # Ищем точное совпадение в маппинге
    if normalized_name in BRANCH_MAPPING:
        logger.debug(f"Mapped branch '{normalized_name}' to '{BRANCH_MAPPING[normalized_name]}'")
        return BRANCH_MAPPING[normalized_name]
    
    # Ищем частичное совпадение (если название содержит ключевые слова)
    for full_name, short_name in BRANCH_MAPPING.items():
        if full_name.lower() in normalized_name.lower() or normalized_name.lower() in full_name.lower():
            logger.debug(f"Partially mapped branch '{normalized_name}' to '{short_name}' via '{full_name}'")
            return short_name
    
    # Если маппинг не найден, логируем это и возвращаем оригинальное название
    logger.info(f"No mapping found for branch '{normalized_name}', using original name")
    return normalized_name
