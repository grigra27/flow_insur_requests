"""
Сервис для сопоставления названий страховых компаний с закрытым списком
"""

import logging
import re
from typing import Optional, List, Tuple
from difflib import SequenceMatcher

from ..constants import get_matchable_company_names, normalize_company_name


logger = logging.getLogger('insurance_companies')


class CompanyNameMatcher:
    """
    Сервис для сопоставления названий страховых компаний с закрытым списком.
    
    Реализует точное и нечеткое сопоставление названий компаний,
    логирует процесс сопоставления для аудита.
    """
    
    def __init__(self, similarity_threshold: float = 0.8):
        """
        Инициализация сервиса сопоставления
        
        Args:
            similarity_threshold: Порог схожести для нечеткого сопоставления (0.0-1.0)
        """
        self.valid_companies = get_matchable_company_names()
        self.similarity_threshold = similarity_threshold
        
        # Создаем словарь для быстрого поиска (нормализованное название -> оригинальное)
        self._normalized_mapping = {}
        for company in self.valid_companies:
            normalized = self._normalize_for_matching(company)
            self._normalized_mapping[normalized] = company
        
        logger.info(f"CompanyNameMatcher инициализирован с {len(self.valid_companies)} компаниями")
    
    def match_company_name(self, input_name: str) -> str:
        """
        Сопоставляет входное название с закрытым списком страховых компаний
        
        Args:
            input_name: Название компании из внешнего источника
            
        Returns:
            Стандартизированное название компании или "другое" если совпадение не найдено
        """
        if not input_name:
            logger.debug("Пустое название компании, возвращаем 'другое'")
            return 'другое'
        
        # Нормализуем входное название
        normalized_input = normalize_company_name(input_name)
        if not normalized_input:
            logger.debug(f"Название '{input_name}' после нормализации стало пустым, возвращаем 'другое'")
            return 'другое'
        
        logger.debug(f"Начинаем сопоставление для '{normalized_input}'")
        
        # 1. Точное совпадение
        exact_match = self._find_exact_match(normalized_input)
        if exact_match:
            logger.info(f"Точное совпадение: '{input_name}' -> '{exact_match}'")
            return exact_match
        
        # 2. Нечеткое сопоставление
        fuzzy_match = self._find_fuzzy_match(normalized_input)
        if fuzzy_match:
            logger.info(f"Нечеткое совпадение: '{input_name}' -> '{fuzzy_match}'")
            return fuzzy_match
        
        # 3. Если совпадений не найдено
        logger.warning(f"Название компании '{input_name}' не найдено в списке, присваиваем 'другое'")
        return 'другое'
    
    def _find_exact_match(self, input_name: str) -> Optional[str]:
        """
        Ищет точное совпадение названия компании
        
        Args:
            input_name: Нормализованное название для поиска
            
        Returns:
            Найденное название компании или None
        """
        # Прямое совпадение
        if input_name in self.valid_companies:
            return input_name
        
        # Совпадение без учета регистра
        normalized_input = self._normalize_for_matching(input_name)
        if normalized_input in self._normalized_mapping:
            return self._normalized_mapping[normalized_input]
        
        return None
    
    def _find_fuzzy_match(self, input_name: str) -> Optional[str]:
        """
        Ищет нечеткое совпадение названия компании
        
        Args:
            input_name: Нормализованное название для поиска
            
        Returns:
            Найденное название компании или None
        """
        normalized_input = self._normalize_for_matching(input_name)
        best_match = None
        best_similarity = 0.0
        
        for company in self.valid_companies:
            normalized_company = self._normalize_for_matching(company)
            
            # Вычисляем схожесть строк
            similarity = SequenceMatcher(None, normalized_input, normalized_company).ratio()
            
            if similarity > best_similarity and similarity >= self.similarity_threshold:
                best_similarity = similarity
                best_match = company
        
        if best_match:
            logger.debug(f"Лучшее нечеткое совпадение для '{input_name}': '{best_match}' (схожесть: {best_similarity:.2f})")
        
        return best_match
    
    def _normalize_for_matching(self, name: str) -> str:
        """
        Нормализует название для сопоставления (приводит к нижнему регистру, убирает лишние символы)
        
        Args:
            name: Исходное название
            
        Returns:
            Нормализованное название для сопоставления
        """
        if not name:
            return ''
        
        # Приводим к нижнему регистру и убираем лишние пробелы
        normalized = name.lower().strip()
        
        # Убираем множественные пробелы
        normalized = re.sub(r'\s+', ' ', normalized)
        
        # Убираем некоторые символы, которые могут мешать сопоставлению
        normalized = re.sub(r'["\'\-\.]', '', normalized)
        
        return normalized
    
    def get_matching_statistics(self, input_names: List[str]) -> dict:
        """
        Возвращает статистику сопоставления для списка названий
        
        Args:
            input_names: Список названий для анализа
            
        Returns:
            Словарь со статистикой сопоставления
        """
        stats = {
            'total': len(input_names),
            'exact_matches': 0,
            'fuzzy_matches': 0,
            'no_matches': 0,
            'matches_detail': []
        }
        
        for name in input_names:
            if not name:
                continue
                
            normalized_input = normalize_company_name(name)
            exact_match = self._find_exact_match(normalized_input)
            
            if exact_match:
                stats['exact_matches'] += 1
                match_type = 'exact'
                result = exact_match
            else:
                fuzzy_match = self._find_fuzzy_match(normalized_input)
                if fuzzy_match:
                    stats['fuzzy_matches'] += 1
                    match_type = 'fuzzy'
                    result = fuzzy_match
                else:
                    stats['no_matches'] += 1
                    match_type = 'none'
                    result = 'другое'
            
            stats['matches_detail'].append({
                'input': name,
                'result': result,
                'match_type': match_type
            })
        
        logger.info(f"Статистика сопоставления: {stats['exact_matches']} точных, "
                   f"{stats['fuzzy_matches']} нечетких, {stats['no_matches']} не найдено")
        
        return stats
    
    def validate_company_list(self) -> List[str]:
        """
        Проверяет список компаний на наличие потенциальных дубликатов
        
        Returns:
            Список предупреждений о возможных дубликатах
        """
        warnings = []
        normalized_companies = {}
        
        for company in self.valid_companies:
            normalized = self._normalize_for_matching(company)
            if normalized in normalized_companies:
                warning = f"Потенциальный дубликат: '{company}' и '{normalized_companies[normalized]}'"
                warnings.append(warning)
                logger.warning(warning)
            else:
                normalized_companies[normalized] = company
        
        return warnings


def create_company_matcher(similarity_threshold: float = 0.8) -> CompanyNameMatcher:
    """
    Фабричная функция для создания экземпляра CompanyNameMatcher
    
    Args:
        similarity_threshold: Порог схожести для нечеткого сопоставления
        
    Returns:
        Настроенный экземпляр CompanyNameMatcher
    """
    return CompanyNameMatcher(similarity_threshold=similarity_threshold)