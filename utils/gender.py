# utils/gender.py
"""
Утилита для подстановки правильных форм слов в зависимости от пола пользователя.
gender: 'M' — мужской, 'F' — женский
"""

def g(gender: str, male: str, female: str) -> str:
    """Выбрать форму слова по полу. g(gender, 'готов', 'готова')"""
    return male if gender == "M" else female

def greet_name(name: str, gender: str) -> str:
    """Обращение по имени с учётом пола."""
    return name  # имя не склоняем — пользователь сам ввёл

def fmt(template: str, name: str, gender: str) -> str:
    """
    Форматирует шаблон, подставляя имя и гендерные формы.
    В шаблоне используй:
      {name}  — имя пользователя
      {г:слово_м|слово_ж}  — гендерная форма
    Пример: "Ты {г:готов|готова}, {name}?"
    """
    import re
    result = template.replace("{name}", name)
    result = re.sub(
        r"\{г:([^|]+)\|([^}]+)\}",
        lambda m: m.group(1) if gender == "M" else m.group(2),
        result
    )
    return result
