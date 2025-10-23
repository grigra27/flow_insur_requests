# Generated migration for standardizing insurance company names

from django.db import migrations
from django.db.models import Q
import logging


logger = logging.getLogger('insurance_companies')


def standardize_company_names(apps, schema_editor):
    """
    Приводит существующие названия компаний в соответствие с закрытым списком
    
    Требования: 4.1, 4.2, 4.3, 4.4
    """
    InsuranceOffer = apps.get_model('summaries', 'InsuranceOffer')
    
    # Список валидных компаний из constants.py (без пустого значения и "другое")
    valid_companies = [
        'Абсолют', 'Альфа', 'ВСК', 'Согаз', 'РЕСО', 'Ингосстрах',
        'Ренессанс', 'Росгосстрах', 'Пари', 'Совкомбанк СК',
        'Согласие', 'Энергогарант', 'ПСБ-страхование', 'Зетта'
    ]
    
    # Статистика миграции
    migration_stats = {
        'total_offers': 0,
        'exact_matches': 0,
        'case_insensitive_matches': 0,
        'mapped_to_other': 0,
        'unchanged': 0,
        'companies_mapped_to_other': [],
        'case_corrections': []
    }
    
    # Получаем все предложения
    all_offers = InsuranceOffer.objects.all()
    migration_stats['total_offers'] = all_offers.count()
    
    print(f"Начинаем миграцию {migration_stats['total_offers']} предложений...")
    
    # Обрабатываем каждое предложение
    for offer in all_offers:
        original_name = offer.company_name
        
        if not original_name:
            # Пустое название - присваиваем "другое"
            offer.company_name = 'другое'
            offer.save(update_fields=['company_name'])
            migration_stats['mapped_to_other'] += 1
            if 'пустое название' not in migration_stats['companies_mapped_to_other']:
                migration_stats['companies_mapped_to_other'].append('пустое название')
            continue
        
        # Проверяем точное совпадение
        if original_name in valid_companies:
            migration_stats['exact_matches'] += 1
            migration_stats['unchanged'] += 1
            continue
        
        # Проверяем совпадение без учета регистра
        matched_company = None
        for company in valid_companies:
            if original_name.lower().strip() == company.lower().strip():
                matched_company = company
                break
        
        if matched_company:
            # Найдено совпадение без учета регистра - исправляем
            offer.company_name = matched_company
            offer.save(update_fields=['company_name'])
            migration_stats['case_insensitive_matches'] += 1
            migration_stats['case_corrections'].append({
                'original': original_name,
                'corrected': matched_company
            })
            continue
        
        # Не найдено совпадений - присваиваем "другое"
        offer.company_name = 'другое'
        offer.save(update_fields=['company_name'])
        migration_stats['mapped_to_other'] += 1
        if original_name not in migration_stats['companies_mapped_to_other']:
            migration_stats['companies_mapped_to_other'].append(original_name)
    
    # Выводим отчет о миграции
    print("\n" + "="*60)
    print("ОТЧЕТ О МИГРАЦИИ НАЗВАНИЙ СТРАХОВЫХ КОМПАНИЙ")
    print("="*60)
    print(f"Всего обработано предложений: {migration_stats['total_offers']}")
    print(f"Точные совпадения (без изменений): {migration_stats['exact_matches']}")
    print(f"Исправления регистра: {migration_stats['case_insensitive_matches']}")
    print(f"Присвоено значение 'другое': {migration_stats['mapped_to_other']}")
    print(f"Всего без изменений: {migration_stats['unchanged']}")
    
    if migration_stats['case_corrections']:
        print(f"\nИсправления регистра:")
        for correction in migration_stats['case_corrections']:
            print(f"  '{correction['original']}' -> '{correction['corrected']}'")
    
    if migration_stats['companies_mapped_to_other']:
        print(f"\nКомпании, присвоенные как 'другое':")
        for company in migration_stats['companies_mapped_to_other']:
            print(f"  - {company}")
    
    print("\n" + "="*60)
    
    # Логируем результаты
    logger.info(f"Миграция завершена. Обработано {migration_stats['total_offers']} предложений. "
               f"Исправлений: {migration_stats['case_insensitive_matches']}, "
               f"Присвоено 'другое': {migration_stats['mapped_to_other']}")
    
    return migration_stats


def reverse_standardize_company_names(apps, schema_editor):
    """
    Обратная миграция - не выполняется для сохранения данных
    
    Примечание: Обратная миграция не реализована, так как восстановление
    исходных названий компаний может привести к потере данных.
    Если необходимо откатить изменения, используйте резервную копию базы данных.
    """
    print("ВНИМАНИЕ: Обратная миграция названий компаний не поддерживается.")
    print("Для отката изменений используйте резервную копию базы данных.")
    pass


class Migration(migrations.Migration):
    
    dependencies = [
        ('summaries', '0008_update_summary_status_choices'),
    ]
    
    operations = [
        migrations.RunPython(
            standardize_company_names,
            reverse_standardize_company_names,
            hints={'preserve_default': False}
        ),
    ]