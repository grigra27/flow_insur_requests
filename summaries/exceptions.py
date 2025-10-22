"""
Кастомные исключения для модуля summaries
"""


class ExcelProcessingError(Exception):
    """Базовое исключение для ошибок обработки Excel файлов"""
    
    def __init__(self, message="Произошла ошибка при обработке Excel файла"):
        self.message = message
        super().__init__(self.message)
    
    def get_user_message(self):
        """Возвращает понятное пользователю сообщение об ошибке"""
        return self.message


class InvalidFileFormatError(ExcelProcessingError):
    """Исключение для ошибок неверного формата файла"""
    
    def __init__(self, filename=None, expected_format=".xlsx"):
        self.filename = filename
        self.expected_format = expected_format
        super().__init__(self.get_user_message())
    
    def get_user_message(self):
        """Возвращает понятное пользователю сообщение об ошибке"""
        if self.filename:
            return (
                f"Файл '{self.filename}' имеет неверный формат. "
                f"Пожалуйста, загрузите файл в формате {self.expected_format}."
            )
        return (
            f"Загруженный файл имеет неверный формат. "
            f"Пожалуйста, загрузите файл в формате {self.expected_format}."
        )


class MissingDataError(ExcelProcessingError):
    """Исключение для отсутствующих данных в Excel файле"""
    
    def __init__(self, missing_cells=None, missing_fields=None):
        self.missing_cells = missing_cells or []
        self.missing_fields = missing_fields or []
        super().__init__(self.get_user_message())
    
    def get_user_message(self):
        """Возвращает понятное пользователю сообщение об ошибке"""
        if self.missing_cells and self.missing_fields:
            cells_str = ", ".join(self.missing_cells)
            fields_str = ", ".join(self.missing_fields)
            return (
                f"В файле отсутствуют обязательные данные. "
                f"Пустые ячейки: {cells_str}. "
                f"Отсутствующие поля: {fields_str}. "
                f"Пожалуйста, заполните все обязательные поля согласно шаблону."
            )
        elif self.missing_cells:
            cells_str = ", ".join(self.missing_cells)
            return (
                f"В файле отсутствуют данные в обязательных ячейках: {cells_str}. "
                f"Пожалуйста, заполните все обязательные поля согласно шаблону."
            )
        elif self.missing_fields:
            fields_str = ", ".join(self.missing_fields)
            return (
                f"В файле отсутствуют обязательные поля: {fields_str}. "
                f"Пожалуйста, заполните все обязательные поля согласно шаблону."
            )
        return (
            "В файле отсутствуют обязательные данные. "
            "Пожалуйста, заполните все обязательные поля согласно шаблону."
        )


class DuplicateOfferError(Exception):
    """Исключение для дублирования предложений от одной компании на один год"""
    
    def __init__(self, company_name, insurance_year):
        self.company_name = company_name
        self.insurance_year = insurance_year
        super().__init__(self.get_user_message())
    
    def get_user_message(self):
        """Возвращает понятное пользователю сообщение об ошибке"""
        return (
            f"Предложение от компании '{self.company_name}' на {self.insurance_year} год "
            f"уже существует в данном своде. Пожалуйста, отредактируйте существующее "
            f"предложение или выберите другой год страхования."
        )