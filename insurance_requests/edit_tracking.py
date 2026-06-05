"""Трекинг ручных правок оператора в V2-флоу.

Парсер V2 распознаёт данные из Excel и показывает их на странице
предпросмотра, где оператор может поправить любое поле перед сохранением.
Этот модуль вычисляет разницу между тем, что распознал парсер («до»), и
тем, что оператор сохранил вручную («после»).

Сравнение строится по форме предпросмотра, а не по итоговым полям модели:
- «до» — значения, которыми была заполнена форма (parse_result['data'],
  то, что оператор видел на превью);
- «после» — «сырые» отправленные значения (form.cleaned_data), без
  подстановки плейсхолдеров вроде «Клиент не указан», которую делает
  to_request_fields(). Так мы не ловим ложных правок там, где оператор
  ничего не трогал.

Функции чистые (не зависят от конкретного InsuranceRequest), чтобы их было
легко покрыть юнит-тестами. Метаданные полей (подписи, варианты выбора,
типы) берутся прямо из форм предпросмотра, чтобы оставаться в синхроне с
тем, что видит оператор.
"""
from __future__ import annotations

import datetime as _dt
import re
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Tuple

# Плейсхолдеры, которыми to_request_fields() заполняет пустые обязательные
# поля модели. В пространстве распознанных данных («до») их нет, поэтому при
# сравнении с текущим значением модели (точка 3) их нужно свести к пустоте —
# иначе пустое распознавание давало бы ложную «правку после создания».
_PLACEHOLDER_VALUES = {
    'Клиент не указан',
    'Предмет лизинга не указан',
    'Номер ДФА не указан',
}

# Скалярные поля формы, которые не участвуют в сравнении как «правки».
_SCALAR_FIELDS_EXCLUDED = {'draft_id'}
# При наличии распознанных объектов эти поля отслеживаются на уровне
# объекта (в формсете), а не на общем уровне — иначе на превью партии они
# дублировали бы объектные правки.
_SCALAR_FIELDS_OBJECT_LEVEL = {'vehicle_info', 'manufacturing_year'}
# Поля объектной формы, не участвующие в сравнении.
_OBJECT_FIELDS_EXCLUDED = {'skip'}

_WHITESPACE_RE = re.compile(r'\s+')


def _field_meta_from_form(form_class) -> Dict[str, Dict[str, Any]]:
    """Собрать метаданные полей из класса формы.

    Для каждого поля: человекочитаемая подпись, словарь вариантов выбора
    (код → подпись) и флаги типа (булево / числовое). Используется и для
    сравнения значений, и для их отображения.
    """
    from django import forms

    meta: Dict[str, Dict[str, Any]] = {}
    for name, field in form_class.base_fields.items():
        choices = None
        raw_choices = getattr(field, 'choices', None)
        if raw_choices:
            choices = {}
            for code, label in raw_choices:
                choices[str(code)] = str(label)
        meta[name] = {
            'label': str(field.label or name),
            'choices': choices,
            'is_bool': isinstance(field, forms.BooleanField),
            'is_numeric': isinstance(
                field, (forms.IntegerField, forms.DecimalField, forms.FloatField)
            ),
        }
    return meta


def get_scalar_field_meta() -> Dict[str, Dict[str, Any]]:
    """Метаданные полей общей (скалярной) формы предпросмотра."""
    from .forms import ParserV2PreviewForm
    return _field_meta_from_form(ParserV2PreviewForm)


def get_object_field_meta() -> Dict[str, Dict[str, Any]]:
    """Метаданные полей объектной формы предпросмотра."""
    from .forms import ParserV2ObjectForm
    return _field_meta_from_form(ParserV2ObjectForm)


def _numeric_canonical(text: str) -> str:
    """Нормализовать число для сравнения (123.0 == 123.00 == «123,00»)."""
    try:
        value = Decimal(text.replace(',', '.'))
    except (InvalidOperation, ValueError):
        return text
    return format(value.normalize(), 'f')


def _canonical(field_name: str, value: Any, meta: Dict[str, Dict[str, Any]]) -> str:
    """Канонический вид значения для сравнения «до/после».

    Булевы → '1'/'0'. Числовые поля нормализуются как числа (чтобы не
    срабатывать на 2021 vs 2021.0). Остальное приводится к строке со
    схлопыванием пробелов. Числовая нормализация применяется ТОЛЬКО к
    явно числовым полям, иначе ИНН с ведущим нулём потерял бы его.
    """
    field_meta = meta.get(field_name, {})
    if field_meta.get('is_bool'):
        return '1' if value else '0'
    if value is None:
        return ''
    text = _WHITESPACE_RE.sub(' ', str(value).strip())
    if field_meta.get('is_numeric') and text:
        return _numeric_canonical(text)
    return text


def _display_value(field_name: str, value: Any, meta: Dict[str, Dict[str, Any]]) -> str:
    """Человекочитаемое значение для показа оператору."""
    field_meta = meta.get(field_name, {})
    if field_meta.get('is_bool'):
        return 'Да' if value else 'Нет'
    if value is None:
        return ''
    text = str(value).strip()
    choices = field_meta.get('choices')
    if choices and text in choices:
        return choices[text]
    return text


def current_display_value(field_name: str, value: Any, meta: Dict[str, Dict[str, Any]]) -> str:
    """Человекочитаемое ТЕКУЩЕЕ значение поля модели (точка 3) для показа.

    В отличие от `_display_value`, который работает с «сырыми» значениями
    формы, это значение приходит прямо из модели и потому может быть:
    - плейсхолдером (`Клиент не указан` …) — сводим к пустоте, чтобы не
      показывать его как осмысленное значение;
    - объектом date/datetime — форматируем по-московски, иначе str() даёт
      длинную ISO-строку с таймзоной.
    Остальные типы обслуживает общий `_display_value`.
    """
    if isinstance(value, str) and value.strip() in _PLACEHOLDER_VALUES:
        value = ''
    if isinstance(value, _dt.datetime):
        from django.utils import timezone as djtz
        if djtz.is_aware(value):
            value = djtz.localtime(value)
        return value.strftime('%d.%m.%Y %H:%M')
    if isinstance(value, _dt.date):
        return value.strftime('%d.%m.%Y')
    return _display_value(field_name, value, meta)


def _edit_type(before_canonical: str, after_canonical: str) -> str:
    """Категория правки: дозаполнение / очистка / исправление."""
    if not before_canonical and after_canonical:
        return 'filled'
    if before_canonical and not after_canonical:
        return 'cleared'
    return 'changed'


def diff_fields(
    before: Dict[str, Any],
    after: Dict[str, Any],
    field_names: List[str],
    meta: Dict[str, Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Сравнить два набора значений и вернуть список правок.

    Каждая правка — dict с ключами field, label, original, modified,
    edit_type. Значения original/modified — уже отформатированные строки,
    готовые к показу без обращения к choices в шаблоне.
    """
    edits: List[Dict[str, str]] = []
    for name in field_names:
        before_value = before.get(name)
        after_value = after.get(name)
        before_canonical = _canonical(name, before_value, meta)
        after_canonical = _canonical(name, after_value, meta)
        if before_canonical == after_canonical:
            continue
        edits.append({
            'field': name,
            'label': meta.get(name, {}).get('label', name),
            'original': _display_value(name, before_value, meta),
            'modified': _display_value(name, after_value, meta),
            'edit_type': _edit_type(before_canonical, after_canonical),
        })
    return edits


def _scalar_field_names(meta: Dict[str, Dict[str, Any]], has_objects: bool) -> List[str]:
    excluded = set(_SCALAR_FIELDS_EXCLUDED)
    if has_objects:
        excluded |= _SCALAR_FIELDS_OBJECT_LEVEL
    return [name for name in meta if name not in excluded]


def build_edit_tracking(
    parse_result: Dict[str, Any],
    scalar_after: Dict[str, Any],
    object_pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]],
    has_objects: bool,
) -> Dict[str, Any]:
    """Построить блок tracking для additional_data['parser_v2'].

    Args:
        parse_result: результат парсера (to_session_dict), «до» берётся из
            parse_result['data'].
        scalar_after: form.cleaned_data общей формы предпросмотра («после»).
        object_pairs: список пар (before_object, after_object) для каждого
            СОЗДАВАЕМОГО объекта (пропущенные через skip уже отфильтрованы),
            в порядке создания. Позиция в списке соответствует item_no.
        has_objects: были ли распознаны объекты лизинга (влияет на то,
            отслеживаются ли vehicle_info/manufacturing_year на общем уровне).

    Returns:
        dict со структурой:
            field_edits: правки общих полей (одинаковы для всех сестёр партии);
            object_edits: список списков правок по объектам (по позиции = item_no);
            summary: агрегаты для аналитики.
    """
    scalar_meta = get_scalar_field_meta()
    object_meta = get_object_field_meta()

    before_scalar = parse_result.get('data') or {}
    scalar_fields = _scalar_field_names(scalar_meta, has_objects)
    field_edits = diff_fields(before_scalar, scalar_after, scalar_fields, scalar_meta)

    object_field_names = [
        name for name in object_meta if name not in _OBJECT_FIELDS_EXCLUDED
    ]
    object_edits: List[List[Dict[str, str]]] = []
    for before_obj, after_obj in object_pairs:
        object_edits.append(
            diff_fields(before_obj, after_obj, object_field_names, object_meta)
        )

    # «Before»-снимок каждого создаваемого объекта (в порядке создания =
    # item_no). Нужен странице сравнения, чтобы показать полную объектную
    # таблицу «распознано / итог» без обратного восстановления позиций.
    object_originals = [dict(before_obj) for before_obj, _ in object_pairs]

    total_object_edits = sum(len(edits) for edits in object_edits)
    return {
        'field_edits': field_edits,
        'object_edits': object_edits,
        'object_originals': object_originals,
        'summary': {
            'total_field_edits': len(field_edits),
            'total_object_edits': total_object_edits,
            'total_edits': len(field_edits) + total_object_edits,
            'edited_field_names': [edit['field'] for edit in field_edits],
        },
    }


def _comparison_rows(
    original: Dict[str, Any],
    edits: List[Dict[str, str]],
    field_names: List[str],
    meta: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Полная таблица сравнения поверх уже посчитанных правок.

    Источник истины для флага «изменено» — список edits (field_edits или
    object_edits), посчитанный при сохранении из «сырых» значений формы.
    Так страница строго согласована с блоком правок в карточке и не ловит
    ложных расхождений из-за нормализации to_request_fields(). Неизменённые
    поля показываются из снимка распознанных данных (одинаково в обеих
    колонках — оператор их не трогал).
    """
    edits_by_field = {edit['field']: edit for edit in edits}
    rows: List[Dict[str, Any]] = []
    for name in field_names:
        edit = edits_by_field.get(name)
        if edit is not None:
            rows.append({
                'field': name,
                'label': edit['label'],
                'original': edit['original'],
                'modified': edit['modified'],
                'changed': True,
                'edit_type': edit['edit_type'],
            })
        else:
            display = _display_value(name, (original or {}).get(name), meta)
            rows.append({
                'field': name,
                'label': meta.get(name, {}).get('label', name),
                'original': display,
                'modified': display,
                'changed': False,
                'edit_type': '',
            })
    return rows


def scalar_comparison_rows(
    original_data: Dict[str, Any],
    field_edits: List[Dict[str, str]],
    has_objects: bool,
) -> List[Dict[str, Any]]:
    """Строки сравнения общих (скалярных) полей для страницы сравнения."""
    meta = get_scalar_field_meta()
    field_names = _scalar_field_names(meta, has_objects)
    return _comparison_rows(original_data, field_edits, field_names, meta)


def object_comparison_rows(
    object_original: Dict[str, Any],
    object_edits: List[Dict[str, str]],
) -> List[Dict[str, Any]]:
    """Строки сравнения объектных полей одной заявки."""
    meta = get_object_field_meta()
    field_names = [name for name in meta if name not in _OBJECT_FIELDS_EXCLUDED]
    return _comparison_rows(object_original, object_edits, field_names, meta)
