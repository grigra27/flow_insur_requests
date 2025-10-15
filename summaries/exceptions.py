"""
Кастомные исключения для модуля summaries
"""


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