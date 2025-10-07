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
${franshiza_text}${installment_text}${avtozapusk_text}${transportation_text}${construction_work_text}
Необходимый период страхования: ${insurance_period_text}.

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
        # Форматируем время ответа в московском часовом поясе
        response_time = self._format_response_deadline_for_email(data)
        
        # Получаем расширенное описание типа страхования
        insurance_type = data.get('insurance_type', 'КАСКО')
        insurance_description = self._get_insurance_type_description(insurance_type)
        
        # Получаем текстовое описание периода страхования
        insurance_period_text = self._format_insurance_period_text(data)
        
        # Базовые данные
        template_data = {
            'ins_type': insurance_description,
            'inn': data.get('inn', '[ИНН не указан]'),
            'insurance_period_text': insurance_period_text,
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
        
        # Transportation and construction work parameters
        template_data['transportation_text'] = (
            'Обратите внимание, требуется страхование перевозки (с погрузкой, выгрузкой) от поставщика к лизингополучателю.\n'
            if data.get('has_transportation') else ''
        )
        
        template_data['construction_work_text'] = (
            'Обратите внимание, требуется страхование монтажных (строительно-монтажных) работ на площадке ЛП по установке оборудования.\n'
            if data.get('has_construction_work') else ''
        )
        
        return template_data
    
    def _format_insurance_period_text(self, data: Dict[str, Any]) -> str:
        """
        Форматирует период страхования для использования в email.
        Поддерживает только стандартизированные варианты.
        """
        insurance_period = data.get('insurance_period', '').strip()
        
        if insurance_period in ['1 год', 'на весь срок лизинга']:
            return insurance_period
        
        return "не указан"

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
        Генерирует тему письма по шаблону "заявка ДФА - Филиал - Информация о предмете лизинга - порядковый номер письма"
        
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
        
        return f"заявка {dfa_number} - {branch} - {vehicle_info} - {sequence_number}"