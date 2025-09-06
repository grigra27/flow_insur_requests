"""
Генерация писем по шаблонам
"""
from typing import Dict, Any
import logging
from string import Template

logger = logging.getLogger(__name__)


class EmailTemplateGenerator:
    """Класс для генерации писем по шаблонам"""
    
    # Маппинг типов страхования на расширенные описания для писем
    INSURANCE_TYPE_DESCRIPTIONS = {
    'КАСКО': (
        'по КАСКО. '
    ),
    'страхование спецтехники': (
        'по страхованию спецтехники (максимальный пакет с транспортировкой (погрузкой/выгрузкой) на весь срок '
        'страхования, согласованный ранее с вашим ГО).\n Напоминаем, что риск кражи / угона в ночное время с '
        'неохраняемой стоянки должен быть включен в предложенный тариф. Также должны быть включены риск просадки '
        'грунта, провала дорог или мостов, обвала тоннелей и риск провала под лед, затопления специальной техники, '
        'дополнительного оборудования.'
    ),
    'страхование имущества': (
        'о страхованию имущества (“полный пакет рисков”). Просим в ответном письме с условиями страхования '
        'указать:\n'
        '1. Будут ли включены в полис риски РНПК\n'
        '2. Есть ли у вас ограничения по выплате страхового возмещения в той степени, в которой предоставление '
        'такого покрытия, возмещение такого убытка или предоставление такой компенсации подвергло бы Страховщика '
        'действиям любых санкций, запретов или ограничений установленных (резолюциями Организации Объединенных '
        'Наций; законами или правилами Европейского союза, Соединенного Королевства Великобритании или Соединенных '
        'Штатов Америки; законодательством РФ, указами Президента РФ и/или иными нормативными подзаконными актами '
        'РФ, принятыми в соответствии с резолюциями СБ ООН, указами Президента РФ и/или иными нормативными '
        'подзаконными актами РФ).\n'
        '3. Просим указать наличие рисков\n'
        '   а) Бой стекол, с указанием включен ли он в данный тариф и данное предложение или требует дополнительной '
        'оплаты – укажите какой.\n'
        '   б) Риск повреждения животными с обязательным указанием, включен ли он в данный тариф и предложение или '
        'требует дополнительной оплаты – укажите какой.'
    ),
    'другое': 'страхованию предмета лизинга.'
}
    
    DEFAULT_TEMPLATE = """Добрый день, уважаемые коллеги!

Высылаем заявку на расчет тарифов ${ins_type}${casco_type_ce}
${franshiza_text}${installment_text}${avtozapusk_text}
Срок страхования: ${formatted_period}.

Для проверки клиента обратите внимание на его ИНН – ${inn}.
Данные просим вписать в прилагаемую таблицу, с занесением данных за каждый период страхования (по годам). Просим в таблице не использовать формулы, просто заполнить предлагаемые параметры.

Ждем Ваше предложение по страховым суммам и страховым премиям по годам до ${response_time} г.

Заранее благодарим.
С Уважением,
ОН-ЛАЙН брокер"""
    
    def __init__(self, template_path: str = None):
        """
        Инициализация генератора шаблонов
        
        Args:
            template_path: Путь к файлу шаблона (опционально)
        """
        self.template = self._load_template(template_path) if template_path else self.DEFAULT_TEMPLATE
    
    def _load_template(self, template_path: str) -> str:
        """Загружает шаблон из файла"""
        try:
            with open(template_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Error loading template from {template_path}: {str(e)}")
            return self.DEFAULT_TEMPLATE
    
    def _get_insurance_type_description(self, insurance_type: str) -> str:
        """
        Получить расширенное описание типа страхования
        
        Args:
            insurance_type: Тип страхования
            
        Returns:
            Расширенное описание типа страхования или оригинальное название как fallback
        """
        return self.INSURANCE_TYPE_DESCRIPTIONS.get(insurance_type, insurance_type)
    
    def generate_email_body(self, data: Dict[str, Any]) -> str:
        """
        Генерирует текст письма на основе данных заявки
        
        Args:
            data: Словарь с данными заявки
            
        Returns:
            Сгенерированный текст письма
        """
        try:
            # Подготавливаем данные для подстановки
            template_data = self._prepare_template_data(data)
            
            # Создаем Template объект и выполняем подстановку
            template = Template(self.template)
            email_body = template.safe_substitute(template_data)
            
            logger.info("Email body generated successfully")
            return email_body
            
        except Exception as e:
            logger.error(f"Error generating email body: {str(e)}")
            raise
    
    def _prepare_template_data(self, data: Dict[str, Any]) -> Dict[str, str]:
        """
        Подготавливает данные для подстановки в шаблон
        
        Args:
            data: Исходные данные заявки
            
        Returns:
            Подготовленные данные для шаблона
        """
        # Форматируем период страхования (старый формат для обратной совместимости)
        insurance_period = self._format_insurance_period_for_email(data)
        
        # Форматируем время ответа в московском часовом поясе
        response_time = self._format_response_deadline_for_email(data)
        
        # Получаем расширенное описание типа страхования
        insurance_type = data.get('insurance_type', 'КАСКО')
        insurance_description = self._get_insurance_type_description(insurance_type)
        
        # Получаем отдельные даты страхования
        start_date = data.get('insurance_start_date')
        end_date = data.get('insurance_end_date')
        
        # Форматируем отдельные даты для нового формата
        formatted_start_date = self._format_date(start_date) if start_date else 'не указано'
        formatted_end_date = self._format_date(end_date) if end_date else 'не указано'
        
        # Форматируем период страхования для нового формата
        formatted_period = self._format_insurance_period(start_date, end_date)
        
        # Базовые данные
        template_data = {
            'ins_type': insurance_description,
            'inn': data.get('inn', '[ИНН не указан]'),
            'srok': insurance_period,  # Старый формат для обратной совместимости
            'insurance_start_date': formatted_start_date,
            'insurance_end_date': formatted_end_date,
            'formatted_period': formatted_period,
            'response_time': response_time,
        }
        
        # Условные блоки текста
        template_data['franshiza_text'] = (
            'Обратите внимание, требуется тариф с франшизой.\n'
            if data.get('has_franchise') else ''
        )
        
        template_data['installment_text'] = (
            'Обратите внимание, требуется рассрочка платежа.\n'
            if data.get('has_installment') else ''
        )
        
        template_data['avtozapusk_text'] = (
            'Обратите внимание, у предмета лизинга имеется автозапуск.\n'
            if data.get('has_autostart') else ''
        )
        
        template_data['casco_type_ce'] = (
            'Обратите внимание, что лизинговое имущество относится к категории'
        ' C/E и требуется страхование с доп. рисками:\n'
        '- страхование вне дорог общего пользования,\n'
        '- провал грунта,\n'
        '- переворот\n'
        '- опрокидывание. \n'
        'Просим Вас указывать, что тарифы даны с расширенными рисками.'
            if data.get('has_casco_ce') else ''
        )
        
        return template_data
    
    def _format_date(self, date_obj) -> str:
        """
        Форматирует дату в формат DD.MM.YYYY
        
        Args:
            date_obj: Объект даты или строка
            
        Returns:
            Отформатированная дата в формате DD.MM.YYYY
        """
        if not date_obj:
            return 'не указано'
        
        # Если это объект date, форматируем его
        if hasattr(date_obj, 'strftime'):
            return date_obj.strftime('%d.%m.%Y')
        
        # Если это строка, возвращаем как есть
        return str(date_obj)
    
    def _format_insurance_period(self, start_date, end_date) -> str:
        """
        Форматирует период страхования для нового формата
        
        Args:
            start_date: Дата начала страхования
            end_date: Дата окончания страхования
            
        Returns:
            Отформатированный период страхования
        """
        if start_date and end_date:
            start_str = self._format_date(start_date)
            end_str = self._format_date(end_date)
            return f"с {start_str} по {end_str}"
        elif start_date:
            start_str = self._format_date(start_date)
            return f"с {start_str} по не указано"
        elif end_date:
            end_str = self._format_date(end_date)
            return f"с не указано по {end_str}"
        else:
            return "не указан"
    
    def _format_insurance_period_for_email(self, data: Dict[str, Any]) -> str:
        """
        Форматирует период страхования для использования в email.
        Использует новые поля дат, если они доступны, иначе старое поле.
        
        Args:
            data: Данные заявки
            
        Returns:
            Отформатированный период страхования в формате "с [date1] по [date2]"
        """
        # Проверяем, есть ли отдельные даты
        start_date = data.get('insurance_start_date')
        end_date = data.get('insurance_end_date')
        
        if start_date and end_date:
            # Если это объекты date, форматируем их
            if hasattr(start_date, 'strftime'):
                start_str = start_date.strftime('%d.%m.%Y')
            else:
                start_str = str(start_date)
            
            if hasattr(end_date, 'strftime'):
                end_str = end_date.strftime('%d.%m.%Y')
            else:
                end_str = str(end_date)
            
            return f"с {start_str} по {end_str}"
        
        # Fallback на старое поле insurance_period
        insurance_period = data.get('insurance_period')
        if insurance_period:
            return str(insurance_period)
        
        # Если ничего нет, возвращаем значение по умолчанию
        return "с 01.01.2024 по 01.01.2025"
    
    def _format_response_deadline_for_email(self, data: Dict[str, Any]) -> str:
        """
        Форматирует срок ответа для использования в email с московским временем.
        
        Args:
            data: Данные заявки
            
        Returns:
            Отформатированный срок ответа в московском времени
        """
        response_deadline = data.get('response_deadline')
        
        if not response_deadline:
            return '[дата не указана]'
        
        # Если это строка, возвращаем как есть (уже отформатировано в to_dict)
        if isinstance(response_deadline, str):
            return response_deadline
        
        # Если это datetime объект, форматируем в московском времени
        try:
            from django.utils import timezone
            import pytz
            
            moscow_tz = pytz.timezone('Europe/Moscow')
            if hasattr(response_deadline, 'astimezone'):
                moscow_time = response_deadline.astimezone(moscow_tz)
                return moscow_time.strftime('%H:%M %d.%m.%Y г.')
            else:
                return str(response_deadline)
        except Exception as e:
            logger.warning(f"Error formatting response deadline: {e}")
            return str(response_deadline)
    
    def generate_subject(self, data: Dict[str, Any], sequence_number: int = 1) -> str:
        """
        Генерирует тему письма по шаблону "ДФА - Филиал - Информация о предмете лизинга - порядковый номер письма"
        
        Args:
            data: Данные заявки
            sequence_number: Порядковый номер письма (по умолчанию 1)
            
        Returns:
            Тема письма
        """
        dfa_number = data.get('dfa_number', 'ДФА не указан')
        branch = data.get('branch', 'Филиал не указан')
        vehicle_info = data.get('vehicle_info', 'Предмет лизинга не указан')
        
        # Ограничиваем длину информации о предмете лизинга для темы письма
        if len(vehicle_info) > 50:
            vehicle_info = vehicle_info[:47] + '...'
        
        return f"{dfa_number} - {branch} - {vehicle_info} - {sequence_number}"