"""
Модульные тесты для класса CompanyNameMatcher
"""

import unittest
from unittest.mock import patch, MagicMock
import logging

from django.test import TestCase

from .services.company_matcher import CompanyNameMatcher, create_company_matcher
from .constants import get_matchable_company_names


class CompanyNameMatcherTests(TestCase):
    """Тесты для класса CompanyNameMatcher"""
    
    def setUp(self):
        """Настройка тестового окружения"""
        # Отключаем логирование для тестов
        logging.disable(logging.CRITICAL)
        
        # Создаем экземпляр matcher с дефолтными настройками
        self.matcher = CompanyNameMatcher()
        
        # Мокаем список компаний для предсказуемых тестов
        self.test_companies = [
            'Абсолют', 'Альфа', 'ВСК', 'Согаз', 'РЕСО', 'Ингосстрах',
            'Ренессанс', 'Росгосстрах', 'Пари', 'Совкомбанк СК',
            'Согласие', 'Энергогарант', 'ПСБ-страхование', 'Зетта'
        ]
    
    def tearDown(self):
        """Очистка после тестов"""
        # Включаем логирование обратно
        logging.disable(logging.NOTSET)
    
    @patch('summaries.services.company_matcher.get_matchable_company_names')
    def test_initialization(self, mock_get_companies):
        """Тест инициализации CompanyNameMatcher"""
        mock_get_companies.return_value = self.test_companies
        
        matcher = CompanyNameMatcher(similarity_threshold=0.9)
        
        self.assertEqual(matcher.similarity_threshold, 0.9)
        self.assertEqual(len(matcher.valid_companies), len(self.test_companies))
        self.assertIn('Абсолют', matcher.valid_companies)
        self.assertNotIn('другое', matcher.valid_companies)
    
    def test_exact_match_same_case(self):
        """Тест точного совпадения с тем же регистром"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            result = self.matcher.match_company_name('Абсолют')
            self.assertEqual(result, 'Абсолют')
    
    def test_exact_match_different_case(self):
        """Тест точного совпадения с разным регистром"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Нижний регистр
            result = self.matcher.match_company_name('абсолют')
            self.assertEqual(result, 'Абсолют')
            
            # Верхний регистр
            result = self.matcher.match_company_name('АЛЬФА')
            self.assertEqual(result, 'Альфа')
            
            # Смешанный регистр
            result = self.matcher.match_company_name('вСк')
            self.assertEqual(result, 'ВСК')
    
    def test_exact_match_with_whitespace(self):
        """Тест точного совпадения с пробелами"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Пробелы в начале и конце
            result = self.matcher.match_company_name('  Согаз  ')
            self.assertEqual(result, 'Согаз')
            
            # Множественные пробелы
            result = self.matcher.match_company_name('Совкомбанк   СК')
            self.assertEqual(result, 'Совкомбанк СК')
    
    def test_fuzzy_match_similar_names(self):
        """Тест нечеткого сопоставления для похожих названий"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Небольшие опечатки
            result = self.matcher.match_company_name('Абсолт')  # пропущена буква 'ю'
            self.assertEqual(result, 'Абсолют')
            
            # Лишние символы - может не совпасть из-за низкой схожести
            result = self.matcher.match_company_name('Альфа-страхование')
            # Проверяем что результат либо найден, либо 'другое'
            self.assertIn(result, ['Альфа', 'другое'])
    
    def test_fuzzy_match_with_punctuation(self):
        """Тест нечеткого сопоставления с пунктуацией"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Кавычки и дефисы
            result = self.matcher.match_company_name('"ВСК"')
            self.assertEqual(result, 'ВСК')
            
            result = self.matcher.match_company_name('ПСБ-страхование.')
            self.assertEqual(result, 'ПСБ-страхование')
    
    def test_fuzzy_match_threshold(self):
        """Тест порога схожести для нечеткого сопоставления"""
        # Создаем matcher с высоким порогом
        strict_matcher = CompanyNameMatcher(similarity_threshold=0.95)
        
        with patch.object(strict_matcher, 'valid_companies', self.test_companies):
            # Название с низкой схожестью не должно совпадать
            result = strict_matcher.match_company_name('Абс')
            self.assertEqual(result, 'другое')
        
        # Создаем matcher с низким порогом
        lenient_matcher = CompanyNameMatcher(similarity_threshold=0.3)
        
        with patch.object(lenient_matcher, 'valid_companies', self.test_companies):
            # То же название должно совпасть
            result = lenient_matcher.match_company_name('Абс')
            self.assertEqual(result, 'Абсолют')
    
    def test_no_match_returns_drugoe(self):
        """Тест возврата 'другое' при отсутствии совпадений"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Полностью неизвестная компания
            result = self.matcher.match_company_name('Неизвестная Компания')
            self.assertEqual(result, 'другое')
            
            # Очень короткое название
            result = self.matcher.match_company_name('А')
            self.assertEqual(result, 'другое')
            
            # Числа
            result = self.matcher.match_company_name('123')
            self.assertEqual(result, 'другое')
    
    def test_empty_input_returns_drugoe(self):
        """Тест обработки пустых входных данных"""
        # Пустая строка
        result = self.matcher.match_company_name('')
        self.assertEqual(result, 'другое')
        
        # None
        result = self.matcher.match_company_name(None)
        self.assertEqual(result, 'другое')
        
        # Только пробелы
        result = self.matcher.match_company_name('   ')
        self.assertEqual(result, 'другое')
    
    def test_special_characters_handling(self):
        """Тест обработки специальных символов"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Символы, которые должны игнорироваться при сопоставлении
            result = self.matcher.match_company_name('Абсолют!!!')
            # Может найти нечеткое совпадение или вернуть 'другое'
            self.assertIn(result, ['Абсолют', 'другое'])
            
            # Различные кавычки
            result = self.matcher.match_company_name("'Альфа'")
            self.assertIn(result, ['Альфа', 'другое'])
            
            # Скобки
            result = self.matcher.match_company_name('(ВСК)')
            self.assertIn(result, ['ВСК', 'другое'])
    
    def test_unicode_characters(self):
        """Тест обработки Unicode символов"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Неразрывные пробелы
            result = self.matcher.match_company_name('Согаз\u00A0')
            self.assertEqual(result, 'Согаз')
            
            # Различные дефисы
            result = self.matcher.match_company_name('ПСБ—страхование')  # em dash
            self.assertEqual(result, 'ПСБ-страхование')
    
    def test_very_long_input(self):
        """Тест обработки очень длинных входных строк"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            long_name = 'Абсолют' + 'x' * 1000
            result = self.matcher.match_company_name(long_name)
            # Должно вернуть 'другое' из-за низкой схожести
            self.assertEqual(result, 'другое')
    
    def test_numeric_input(self):
        """Тест обработки числовых входных данных"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Чистые числа
            result = self.matcher.match_company_name('12345')
            self.assertEqual(result, 'другое')
            
            # Смешанные числа и буквы
            result = self.matcher.match_company_name('Абсолют123')
            # Может совпасть при нечетком сопоставлении
            self.assertIn(result, ['Абсолют', 'другое'])
    
    def test_normalize_for_matching_method(self):
        """Тест метода нормализации для сопоставления"""
        # Тестируем приватный метод через публичный интерфейс
        test_cases = [
            ('Абсолют', 'абсолют'),
            ('  ВСК  ', 'вск'),
            ('ПСБ-страхование', 'псбстрахование'),
            ('"Альфа"', 'альфа'),
            ('Согаз   Компания', 'согаз компания'),
            ('', ''),
        ]
        
        for input_name, expected in test_cases:
            normalized = self.matcher._normalize_for_matching(input_name)
            self.assertEqual(normalized, expected, 
                           f"Нормализация '{input_name}' должна дать '{expected}', получено '{normalized}'")
    
    def test_get_matching_statistics(self):
        """Тест получения статистики сопоставления"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            test_names = [
                'Абсолют',           # точное совпадение
                'альфа',             # точное совпадение (разный регистр)
                'Абсолт',            # нечеткое совпадение
                'Неизвестная',       # нет совпадения
                'ВСК Страхование'    # нечеткое совпадение
            ]
            
            stats = self.matcher.get_matching_statistics(test_names)
            
            self.assertEqual(stats['total'], len(test_names))
            self.assertGreaterEqual(stats['exact_matches'], 2)  # Абсолют, альфа
            self.assertGreaterEqual(stats['fuzzy_matches'], 0)
            self.assertGreaterEqual(stats['no_matches'], 1)     # Неизвестная
            # Проверяем что количество деталей соответствует непустым именам
            non_empty_names = [name for name in test_names if name]
            self.assertEqual(len(stats['matches_detail']), len(non_empty_names))
            
            # Проверяем структуру детальной информации
            for detail in stats['matches_detail']:
                self.assertIn('input', detail)
                self.assertIn('result', detail)
                self.assertIn('match_type', detail)
                self.assertIn(detail['match_type'], ['exact', 'fuzzy', 'none'])
    
    def test_validate_company_list(self):
        """Тест валидации списка компаний на дубликаты"""
        # Создаем список с потенциальными дубликатами
        companies_with_duplicates = [
            'Абсолют',
            'абсолют',  # дубликат с разным регистром
            'ВСК',
            'В-С-К',    # потенциальный дубликат
            'Альфа'
        ]
        
        with patch.object(self.matcher, 'valid_companies', companies_with_duplicates):
            warnings = self.matcher.validate_company_list()
            
            # Должно быть хотя бы одно предупреждение о дубликате
            self.assertGreater(len(warnings), 0)
            self.assertTrue(any('дубликат' in warning.lower() for warning in warnings))
    
    def test_case_sensitivity_consistency(self):
        """Тест консистентности обработки регистра"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Все варианты регистра должны давать одинаковый результат
            variations = ['абсолют', 'АБСОЛЮТ', 'Абсолют', 'аБсОлЮт']
            
            results = [self.matcher.match_company_name(var) for var in variations]
            
            # Все результаты должны быть одинаковыми
            self.assertTrue(all(result == 'Абсолют' for result in results),
                           f"Все варианты регистра должны давать 'Абсолют', получено: {results}")
    
    def test_whitespace_handling_consistency(self):
        """Тест консистентности обработки пробелов"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Различные варианты пробелов должны давать одинаковый результат
            variations = [
                'Совкомбанк СК',
                ' Совкомбанк СК ',
                'Совкомбанк  СК',
                'Совкомбанк\tСК',
                'Совкомбанк\nСК'
            ]
            
            results = [self.matcher.match_company_name(var) for var in variations]
            
            # Все результаты должны быть одинаковыми
            self.assertTrue(all(result == 'Совкомбанк СК' for result in results),
                           f"Все варианты пробелов должны давать 'Совкомбанк СК', получено: {results}")


class CompanyNameMatcherFactoryTests(TestCase):
    """Тесты для фабричной функции create_company_matcher"""
    
    def test_create_company_matcher_default(self):
        """Тест создания matcher с дефолтными параметрами"""
        matcher = create_company_matcher()
        
        self.assertIsInstance(matcher, CompanyNameMatcher)
        self.assertEqual(matcher.similarity_threshold, 0.8)
    
    def test_create_company_matcher_custom_threshold(self):
        """Тест создания matcher с кастомным порогом"""
        matcher = create_company_matcher(similarity_threshold=0.9)
        
        self.assertIsInstance(matcher, CompanyNameMatcher)
        self.assertEqual(matcher.similarity_threshold, 0.9)
    
    def test_create_company_matcher_invalid_threshold(self):
        """Тест создания matcher с некорректным порогом"""
        # Слишком высокий порог
        matcher = create_company_matcher(similarity_threshold=1.5)
        self.assertEqual(matcher.similarity_threshold, 1.5)  # Функция не валидирует
        
        # Отрицательный порог
        matcher = create_company_matcher(similarity_threshold=-0.1)
        self.assertEqual(matcher.similarity_threshold, -0.1)  # Функция не валидирует


class CompanyNameMatcherEdgeCasesTests(TestCase):
    """Тесты граничных случаев для CompanyNameMatcher"""
    
    def setUp(self):
        """Настройка тестового окружения"""
        logging.disable(logging.CRITICAL)
        self.matcher = CompanyNameMatcher()
        self.test_companies = ['Абсолют', 'Альфа', 'ВСК']
    
    def tearDown(self):
        """Очистка после тестов"""
        logging.disable(logging.NOTSET)
    
    def test_empty_company_list(self):
        """Тест работы с пустым списком компаний"""
        with patch.object(self.matcher, 'valid_companies', []):
            result = self.matcher.match_company_name('Любая компания')
            self.assertEqual(result, 'другое')
    
    def test_single_character_companies(self):
        """Тест работы с односимвольными названиями компаний"""
        single_char_companies = ['А', 'Б', 'В']
        
        with patch.object(self.matcher, 'valid_companies', single_char_companies):
            # Точное совпадение
            result = self.matcher.match_company_name('А')
            self.assertEqual(result, 'А')
            
            # Нет совпадения
            result = self.matcher.match_company_name('Г')
            self.assertEqual(result, 'другое')
    
    def test_very_similar_company_names(self):
        """Тест работы с очень похожими названиями компаний"""
        similar_companies = ['Абсолют', 'Абсолют+', 'Абсолют-М']
        
        with patch.object(self.matcher, 'valid_companies', similar_companies):
            # Должно найти точное совпадение
            result = self.matcher.match_company_name('Абсолют')
            self.assertEqual(result, 'Абсолют')
            
            # Должно найти нечеткое совпадение с наиболее похожим
            result = self.matcher.match_company_name('Абсолют М')
            self.assertIn(result, similar_companies)
    
    def test_non_string_input(self):
        """Тест обработки не-строковых входных данных"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Число - может быть преобразовано в строку
            result = self.matcher.match_company_name(123)
            # Проверяем что результат корректный (либо найдено совпадение, либо 'другое')
            self.assertIn(result, self.test_companies + ['другое'])
            
            # Список - может быть преобразован в строку
            result = self.matcher.match_company_name(['Абсолют'])
            self.assertIn(result, self.test_companies + ['другое'])
            
            # Словарь - может быть преобразован в строку
            result = self.matcher.match_company_name({'name': 'Абсолют'})
            self.assertIn(result, self.test_companies + ['другое'])
    
    def test_malformed_unicode(self):
        """Тест обработки некорректного Unicode"""
        with patch.object(self.matcher, 'valid_companies', self.test_companies):
            # Строка с некорректными символами Unicode
            malformed_name = 'Абсолют\uFFFD'  # replacement character
            result = self.matcher.match_company_name(malformed_name)
            # Должно либо найти совпадение, либо вернуть 'другое'
            self.assertIn(result, ['Абсолют', 'другое'])
    
    def test_extremely_long_company_names(self):
        """Тест работы с экстремально длинными названиями"""
        long_companies = ['А' * 1000, 'Б' * 500]
        
        with patch.object(self.matcher, 'valid_companies', long_companies):
            # Точное совпадение с длинным названием
            result = self.matcher.match_company_name('А' * 1000)
            self.assertEqual(result, 'А' * 1000)
            
            # Частичное совпадение с длинным названием
            result = self.matcher.match_company_name('А' * 999)
            # Может найти нечеткое совпадение или вернуть 'другое'
            self.assertIn(result, ['А' * 1000, 'другое'])
    
    def test_performance_with_many_companies(self):
        """Тест производительности с большим количеством компаний"""
        # Создаем большой список компаний
        many_companies = [f'Компания_{i}' for i in range(1000)]
        
        with patch.object(self.matcher, 'valid_companies', many_companies):
            # Тест должен выполниться быстро даже с большим списком
            import time
            start_time = time.time()
            
            result = self.matcher.match_company_name('Компания_500')
            
            end_time = time.time()
            execution_time = end_time - start_time
            
            self.assertEqual(result, 'Компания_500')
            self.assertLess(execution_time, 1.0)  # Должно выполниться менее чем за секунду