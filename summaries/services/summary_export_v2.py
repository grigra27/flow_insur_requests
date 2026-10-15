"""Свод котировок V2 (бета, только суперпользователь).

Содержание то же, что у текущего свода (ExcelExportService + шаблоны templates/*summary*.xlsx):
лист «Свод» уходит клиенту, полная версия добавляет лист «Параметры запроса» для коллег
из лизинговой компании. Отличия — только в подаче.

Оформление «Ценники» (выбрано владельцем 2026-10-12 из десяти вариантов):

- слева направо: страховая компания → ИТОГО за срок крупными «ценниками» (по предложению) →
  детализация по годам мелким шрифтом → территория, ответы СК, комментарии;
- в детализации сначала условие, потом результат: франшиза → тариф → премия → платежей в год;
- строки с цифрами одной высоты; длинный текст территории/комментариев продолжается
  в добавочную строку в конце блока СК, а не растягивает строки лет;
- white label: ни бренда, ни контактов, ни аналитики; палитра «индиго»;
- СК отсортированы по ИТОГО предложения 1;
- «Выбрана СК» / «Выбрано предложение» — ручные жёлтые поля с выпадающими списками;
  выбранная СК подсвечивается условным форматированием;
- подписи «Предложение 1/2» с размером франшизы; вместо служебной «Нет данных: территория
  ранее не собиралась» — «—»; дата свода в шапке; пустое примечание не выводится.

Таблица (2026-10-12): сетка, тёмные линии между СК и между смысловыми блоками колонок, рамка, зебра
по СК; индиго — предложение 1, бирюза — предложение 2, терракота — условия.

Печать — «мягкие» стандартные настройки (решение владельца 2026-10-13), каждая меняется в окне печати Excel
в один клик: A4 альбомная, «вписать все столбцы на одну страницу» (высота — сколько получится), узкие поля,
центрирование, повтор шапки таблицы, номер страницы. Ни области печати, ни фиксированного масштаба, ни ручных
разрывов. На экране закреплены СК и ценники.

Правила данных (примечания, системные комментарии, территория, отказы) берутся у
ExcelExportService, чтобы V1 и V2 не расходились. Старый свод этот модуль не меняет.
"""
from __future__ import annotations

import logging
import math
import re
from datetime import date
from decimal import Decimal
from io import BytesIO
from typing import Dict, List, Tuple

from django.conf import settings
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from core.excel_cached_values import with_cached_values

from ..models import InsuranceSummary, InsurerResponse
from ..response_sections import SECTIONS, required_sections
from .excel_services import ExcelExportService, ExcelExportServiceError

logger = logging.getLogger(__name__)

FONT = 'Arial'
INK = '111827'
MUTED = '6B7280'
INPUT_FILL = PatternFill('solid', fgColor='FFF2B3')  # ручные поля менеджера — всегда жёлтые

# Палитра white label (без фирменных цветов брокера). «Индиго» — из выбранного образца «Ценники»
# (2026-10-12); прежний «деловой синий» и отклонённые графит, изумруд, синий с золотом — в истории git.
# header/header_2 — подписи предложений 1/2 над ценниками и цифры ценников, tag/tag_2 — заливка
# ценников, detail — цифры детализации, chosen* — подсветка выбранной СК и предложения.
PALETTES = {
    'indigo': {
        'title': '312E81', 'header': '312E81', 'header_2': '0F766E', 'tag': 'EEF0FF', 'tag_2': 'E3F3F0',
        'detail': '1F2937', 'column': '4B5563', 'hair': 'E0E3F0', 'block': 'A5ACD6', 'section': 'EEF0FF',
        'chosen': 'EEF2FF', 'chosen_company': 'E0E7FF', 'chosen_total': 'C7D2FE', 'chosen_variant': 'E0E7FF',
        # таблица: сетка, разделитель СК, рамка, шапка, зебра; терракота — блок условий и подпись «Франшиза»; красный — ненулевая франшиза
        'grid': 'D5D9E8', 'separator': '312E81', 'frame': '312E81', 'header_fill': 'F1F2F9',
        'zebra': 'F8F9FD', 'declined_fill': 'F6F6F8', 'cond': 'B4532A', 'cond_fill': 'FBEEE8',
        'franchise': 'C00000',
    },
}
DEFAULT_PALETTE = 'indigo'

MONEY = '#,##0'  # копейки хранятся в ячейке, на экране — целые рубли, как в своде V1
RATE = '0.00%'

HEADER_ROW = 4  # поля шапки: строки 4–8 (заявка, объект, лизингополучатель, цели, примечание)
FIRST_DATA_ROW = 11  # шапка таблицы — строки 9–10
# Детализация чуть крупнее (9 / 8,5 pt) и темнее — отзыв сотрудников 2026-10-14 о мелком шрифте
FONT_SIZES = {'detail': 9, 'text': 8.5, 'column': 8.5, 'company': 12, 'total': 16, 'title': 18, 'field': 11}
SCREEN_ZOOM = 115  # масштаб листа «Свод» при открытии, %: крупнее на экране, на печать не влияет
ROW_HEIGHT = 17  # строка года — всегда одной высоты
TAG_MIN_HEIGHT = 30  # ценник шрифтом 16 pt: блок СК не ниже этого, даже если в нём один год
TEXT_LINE_HEIGHT = 11  # pt на строку текста шрифтом 8.5
DECLINED_ROW_HEIGHT = 22


def _font(size=9, bold=False, italic=False, color=INK):
    return Font(name=FONT, size=size, bold=bold, italic=italic, color=color)


def _text_lines(text, chars_per_line: int) -> int:
    if not text:
        return 0
    return sum(max(1, math.ceil(len(part) / chars_per_line)) for part in str(text).split('\n'))


def col_points(width: float) -> float:
    """Ширина колонки Excel (в символах) в pt: px = width*7+5 при 96 dpi."""
    return int(width * 7 + 5) * 0.75


def text_chars(width: float) -> int:
    """Сколько символов шрифта 8.5 pt помещается в строке колонки шириной width."""
    return max(1, int(width * 1.2))


class SummaryExportV2Service(ExcelExportService):
    """Генерация свода V2 с нуля, без xlsx-шаблона."""

    LEGACY_TERRITORY_V2 = '—'

    WIDTHS = {'company': 20, 'total': 17, 'year': 7, 'sum': 13, 'franchise': 10, 'rate': 8, 'premium': 11,
              'payments': 8, 'territory': 40, 'notes': 48, 'inspection': 14, 'rnpk': 14, 'ce_risks': 14, 'transport': 12}
    DETAIL_KEYS = ('franchise', 'rate', 'premium', 'payments')  # порядок: условие → результат
    DETAIL_TITLES = {'franchise': 'Франшиза', 'rate': 'Тариф', 'premium': 'Премия', 'payments': 'Платежей в год'}

    # Колонки второй страницы между территорией и комментариями (этап 5 плана ответа V2) — блоки реестра,
    # нужные по заявке: «Осмотр» (всегда), «Риски РНПК», «Перевозка». Значения — только из ответа
    # страховщика («Ответ СК»); правило «б/у → осмотр» в своде V2 не используется (решение 2026-10-07)
    EXTRA_TITLES = {section.key: section.summary_column for section in SECTIONS}
    NO_DATA = 'нет данных'
    # Перевозка — отдельная сумма и отдельная оплата: в ИТОГО не входит (решение владельца 2026-10-12)
    TRANSPORT_TITLE = 'Перевозка, ₽\nоплачивается отдельно'
    TRANSPORT_FOOTNOTE = ('* ИТОГО — без перевозки. Страхование перевозки оплачивается отдельно, '
                          'одной суммой, указанной в колонке «Перевозка».')

    def __init__(self, palette: str = DEFAULT_PALETTE):
        self.fs = FONT_SIZES
        self._width_override = {}
        self.palette = PALETTES[palette]
        self.hair = Side(style='thin', color=self.palette['hair'])
        self.block_line = Side(style='medium', color=self.palette['block'])
        self.cell_border = Border(left=self.hair, right=self.hair, top=self.hair, bottom=self.hair)
        # Шаблон V1 не нужен, но базовый __init__ проверяет путь — передаём существующий
        super().__init__(str(settings.BASE_DIR / 'templates' / 'summary_template.xlsx'))

    # ── публичное API ────────────────────────────────────────────────────────

    def generate(self, summary: InsuranceSummary, is_client_version: bool) -> BytesIO:
        try:
            self._validate_summary_data(summary)
            has_variant_2 = self._determine_template_type_safe(summary) == 'full'
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = 'Свод'
            self._build_summary_sheet(sheet, summary, has_variant_2)
            if not is_client_version:
                self._build_request_sheet(workbook.create_sheet('Параметры запроса'), summary.request)
            # white label: без автора/компании в свойствах файла
            workbook.properties.creator = ''
            workbook.properties.lastModifiedBy = ''
            workbook.properties.title = 'Свод котировок'
            output = BytesIO()
            workbook.save(output)
            # готовые значения ИТОГО и тарифов — видны и в «защищённом просмотре» Excel
            return BytesIO(with_cached_values(output.getvalue()))
        except ExcelExportServiceError:
            raise
        except Exception as e:
            logger.error(f"Ошибка генерации свода V2 для свода ID {summary.id}: {e}", exc_info=True)
            raise ExcelExportServiceError(f"Ошибка при генерации свода V2: {e}") from e

    # ── колонки ──────────────────────────────────────────────────────────────

    SERVICE_KEYS = ('totals_last', 'numbers_last', 'last', 'label')  # не колонки, а ссылки на них

    @classmethod
    def columns(cls, has_variant_2: bool, extras=('inspection',)) -> Dict[str, str]:
        variants = [1, 2] if has_variant_2 else [1]
        keys = ['company', *[f'total_{v}' for v in variants], 'year', 'sum']
        for v in variants:
            keys += [f'{key}_{v}' for key in cls.DETAIL_KEYS]
        cols = {key: get_column_letter(i) for i, key in enumerate(keys, start=1)}
        cols['totals_last'] = cols[f'total_{variants[-1]}']  # повторяются на странице условий
        cols['numbers_last'] = get_column_letter(len(keys))  # последняя колонка детализации
        page_two = ['territory', *extras, 'notes']
        for offset, key in enumerate(page_two, start=1):
            cols[key] = get_column_letter(len(keys) + offset)
        cols['last'] = cols['notes']
        cols['label'] = get_column_letter(len(keys) + len(page_two) - 1)  # подписи полей выбора
        return cols

    @staticmethod
    def extra_columns(request) -> List[str]:
        return [section.key for section in required_sections(request)]

    def _fill(self, key: str):
        color = self.palette[key]
        return PatternFill('solid', fgColor=color) if color else None

    def _width(self, key: str) -> float:
        key = re.sub(r'_\d$', '', key)
        return self._width_override.get(key, self.WIDTHS[key])

    # ── лист «Свод» ──────────────────────────────────────────────────────────

    def _build_summary_sheet(self, ws, summary: InsuranceSummary, has_variant_2: bool) -> None:
        extras = self.extra_columns(summary.request)
        cols = self.columns(has_variant_2, extras)
        for key, letter in cols.items():
            if key not in self.SERVICE_KEYS:
                ws.column_dimensions[letter].width = self._width(key)
        ws.sheet_view.showGridLines = False
        extra_values = self._extra_values(summary, extras)

        companies = self._sorted_companies(summary)
        declined = self._get_declined_companies(summary)

        self._build_header(ws, summary, cols, [name for name, _ in companies], has_variant_2)
        self._build_table_header(ws, cols, companies, has_variant_2)

        row = FIRST_DATA_ROW
        blocks: List[Tuple[int, int]] = []
        for name, offers in companies:
            end = self._write_company_block(ws, row, name, offers, cols, has_variant_2, extra_values.get(name, {}))
            blocks.append((row, end))
            row = end + 1
        for name in declined:
            self._write_declined_row(ws, row, name, cols)
            blocks.append((row, row))
            row += 1
        self._apply_table_style(ws, cols, blocks, len(companies), has_variant_2)
        if 'transport' in cols:
            self._write_transport_footnote(ws, row + 1, cols)
            row += 2

        ws.freeze_panes = f'{cols["year"]}{FIRST_DATA_ROW}'  # СК и ценники остаются на экране при прокрутке
        ws.sheet_view.zoomScale = SCREEN_ZOOM
        self._setup_print(ws, cols)

    def _sorted_companies(self, summary: InsuranceSummary) -> List[tuple]:
        companies = self._validate_companies_data(self._get_companies_sorted_data(summary))

        def key(item):
            name, offers = item
            total = self._calculate_premium_sum(offers, 1)
            return (total is None, total or Decimal('0'), name)

        return sorted(companies.items(), key=key)

    def _extra_values(self, summary, extras) -> Dict[str, Dict[str, object]]:
        """Значения доп. колонок по компаниям — из «Ответа СК»: подпись значения из списка или сумма;
        «нет данных», если страховщик не ответил (например, ответ в старом шаблоне)."""
        responses = {r.company_name: r for r in InsurerResponse.objects.filter(summary=summary)}
        values = {}
        for name in summary.offers.values_list('company_name', flat=True).distinct():
            response = responses.get(name)
            row = {}
            for section in SECTIONS:
                if section.key not in extras:
                    continue
                main = section.fields[0]
                value = getattr(response, main.name, None) if response else None
                if value in (None, ''):
                    row[section.key] = self.NO_DATA
                elif main.kind == 'choice':
                    row[section.key] = dict(main.choices).get(value, value)
                else:
                    row[section.key] = value
            row['transport_terms'] = response.transport_terms if response and 'transport' in extras else ''
            row['ce_risks_comment'] = response.ce_risks_comment if response and 'ce_risks' in extras else ''
            values[name] = row
        return values

    @staticmethod
    def selection_cells(cols) -> Tuple[str, str]:
        """Ручные жёлтые поля «Выбрана СК» и «Выбрано предложение» — справа вверху, для менеджера
        (при печати попадают на страницу с территорией и комментариями)."""
        return f'{cols["notes"]}{HEADER_ROW}', f'{cols["notes"]}{HEADER_ROW + 2}'

    def _build_header(self, ws, summary, cols, company_names, has_variant_2) -> None:
        request = summary.request
        value_end = cols['numbers_last']

        ws['A1'] = 'Свод котировок и условий'
        ws['A1'].font = _font(self.fs['title'], bold=True, color=self.palette['title'])
        ws.row_dimensions[1].height = 28
        ws['A2'] = f'от {timezone.localdate():%d.%m.%Y}'
        ws['A2'].font = _font(11, color=MUTED)

        object_text = request.object_summary or ''
        year = (request.manufacturing_year or '').strip()
        if year and year not in object_text and f'{year} г.' not in object_text:
            object_text = f'{object_text}, {year}' if object_text else year

        rows = [
            ('Заявка №', request.dfa_number),
            ('Объект страхования', object_text),
            ('Лизингополучатель', request.client_name),
            ('Цели использования', request.usage_purposes or ''),
        ]
        if (summary.notes or '').strip():  # пустое примечание не показываем — строка остаётся пустой
            rows.append(('Примечание', summary.notes))
        width = sum(self._width(k) for k in cols if k not in (*self.SERVICE_KEYS, 'company', 'territory', 'notes',
                                                            *self.EXTRA_TITLES))
        chars = int(width * 0.95)
        for offset, (label, value) in enumerate(rows):
            r = HEADER_ROW + offset
            ws[f'A{r}'].value = label
            ws[f'A{r}'].font = _font(9, color=MUTED)
            ws[f'A{r}'].alignment = Alignment(vertical='top')
            ws.merge_cells(f'B{r}:{value_end}{r}')
            ws[f'B{r}'].value = self._sanitize_excel_text(value)
            ws[f'B{r}'].font = _font(self.fs['field'], bold=label in ('Заявка №', 'Объект страхования'))
            ws[f'B{r}'].alignment = Alignment(vertical='top', wrap_text=True)
            ws.row_dimensions[r].height = max(17, _text_lines(ws[f'B{r}'].value, chars) * 15)

        # Ручные поля выбора справа: подпись — в колонке перед комментариями, жёлтое поле — в комментариях
        company_cell, variant_cell = self.selection_cells(cols)
        for coord, label in ((company_cell, 'Выбрана СК:'), (variant_cell, 'Выбрано предложение:')):
            row = ws[coord].row
            label_cell = ws[f'{cols["label"]}{row}']
            label_cell.value = label
            label_cell.font = _font(10, bold=True)
            label_cell.alignment = Alignment(horizontal='right', vertical='center')
            target = ws[coord]
            target.fill, target.border = INPUT_FILL, self.cell_border
            target.font = _font(11, bold=True)
            target.alignment = Alignment(vertical='center')

        variants = ['Предложение 1'] + (['Предложение 2'] if has_variant_2 else [])
        for coord, options, prompt in (
            (company_cell, company_names, 'Выберите СК из списка или впишите вручную.'),
            (variant_cell, variants, 'Выберите предложение из списка или впишите вручную.'),
        ):
            formula = '"' + ','.join(name.replace(',', ' ') for name in options) + '"'
            if not options or len(formula) > 255:
                continue
            dv = DataValidation(type='list', formula1=formula, allow_blank=True,
                                showErrorMessage=False, prompt=prompt)
            dv.add(coord)
            ws.add_data_validation(dv)

    def _variant_caption(self, companies, variant: int) -> str:
        values = set()
        for _, offers in companies:
            for offer in offers:
                if variant == 2 and self._format_premium(offer, 2) is None:
                    continue
                franchise = self._format_franchise(offer, variant)
                values.add(franchise if franchise is not None else Decimal('0'))
        if not values:
            return f'Предложение {variant}'
        if len(values) > 1:
            return f'Предложение {variant} · франшиза по предложениям СК'
        value = values.pop()
        if value == 0:
            return f'Предложение {variant} · без франшизы'
        return f'Предложение {variant} · франшиза {value:,.0f}'.replace(',', ' ')

    def _build_table_header(self, ws, cols, companies, has_variant_2) -> None:
        top, sub = FIRST_DATA_ROW - 2, FIRST_DATA_ROW - 1
        ws.row_dimensions[top].height = 18
        # подпись предложения над ценником («… · франшиза по предложениям СК») может занять три строки
        variants = [1, 2] if has_variant_2 else [1]
        caption_lines = max(_text_lines(self._variant_caption(companies, v), text_chars(self.WIDTHS['total']) - 3)
                            for v in variants)
        ws.row_dimensions[sub].height = max(30, caption_lines * TEXT_LINE_HEIGHT + 6)
        accent = self.palette['title']
        center = dict(horizontal='center', vertical='center', wrap_text=True)

        def title(letter, text, color, size, merged=True):
            if merged:
                ws.merge_cells(f'{letter}{top}:{letter}{sub}')
            cell = ws[f'{letter}{top if merged else sub}']
            cell.value = text
            cell.font = _font(size, bold=True, color=color)
            cell.alignment = Alignment(**center)

        title('A', 'Страховая компания', accent, 9)
        ws['A' + str(top)].alignment = Alignment(vertical='center', wrap_text=True)
        first_total, last_total = cols['total_1'], cols['totals_last']
        if first_total != last_total:
            ws.merge_cells(f'{first_total}{top}:{last_total}{top}')
        ws[f'{first_total}{top}'] = 'ИТОГО*' if 'transport' in cols else 'ИТОГО'
        ws[f'{first_total}{top}'].font = _font(9, bold=True, color=accent)
        ws[f'{first_total}{top}'].alignment = Alignment(horizontal='center', vertical='center')
        white = Side(style='medium', color='FFFFFF')
        for v in variants:
            cell = ws[f'{cols[f"total_{v}"]}{sub}']
            cell.value = self._variant_caption(companies, v)
            cell.font = _font(self.fs['detail'], bold=True, color='FFFFFF')
            cell.fill = self._fill('header' if v == 1 else 'header_2')
            cell.alignment = Alignment(horizontal='center', vertical='center', wrap_text=True)
            cell.border = Border(left=white, right=white)

            first, last = cols[f'{self.DETAIL_KEYS[0]}_{v}'], cols[f'{self.DETAIL_KEYS[-1]}_{v}']
            ws.merge_cells(f'{first}{top}:{last}{top}')
            ws[f'{first}{top}'] = f'Детализация · Предложение {v}'
            ws[f'{first}{top}'].font = _font(self.fs['detail'], bold=True, color=MUTED)
            ws[f'{first}{top}'].alignment = Alignment(horizontal='center', vertical='center')
            for key in self.DETAIL_KEYS:
                title(cols[f'{key}_{v}'], self.DETAIL_TITLES[key], self.palette['column'], self.fs['column'], merged=False)

        title(cols['year'], 'Год', self.palette['column'], self.fs['column'])
        title(cols['sum'], 'Страховая сумма', self.palette['column'], self.fs['column'])
        title(cols['territory'], 'Территория страхования', accent, 9)
        for key, text in self.EXTRA_TITLES.items():
            if key in cols:
                title(cols[key], self.TRANSPORT_TITLE if key == 'transport' else text, accent, 9)
        title(cols['notes'], 'Комментарии', accent, 9)

        line = Side(style='medium', color=accent)
        for idx in range(1, ws[f'{cols["last"]}1'].column + 1):
            cell = ws.cell(row=sub, column=idx)
            cell.border = Border(left=cell.border.left, right=cell.border.right, bottom=line)

    def _write_company_block(self, ws, start, name, offers, cols, has_variant_2, extra) -> int:
        """Блок СК: строки по годам (+ добавочная строка, если текст не влез); возвращает последнюю строку."""
        offers = sorted(offers, key=lambda o: o.insurance_year)
        last_year = start + len(offers) - 1
        variants = [1, 2] if has_variant_2 else [1]
        detail = _font(self.fs['detail'], color=self.palette['detail'])
        # Числа детализации — по центру колонок, чтобы разные по длине значения не «плыли» (отзыв сотрудников 2026-10-14)
        center = Alignment(horizontal='center', vertical='center')

        territories = self._block_territories(offers)
        # Системная фраза про осмотр в своде V2 не пишется — осмотр в колонке «Осмотр» (ответ страховщика)
        additional = self._combine_additional_notes(
            self._get_franchise_approval_note_for_company(offers, name),
            f"Условия перевозки: {extra['transport_terms']}" if extra.get('transport_terms') else None,
        )
        if extra.get('ce_risks_comment'):
            additional = self._combine_additional_notes(additional, f"Доп. риски C/E: {extra['ce_risks_comment']}")
        notes = self._consolidate_notes(offers, additional) or ''
        extra_keys = [key for key in self.EXTRA_TITLES if key in cols]

        # Строки лет — одной высоты; текст, который в них не влез, продолжается в добавочной строке
        per_year = len(territories) > 1
        needed_lines = max(
            _text_lines(notes, text_chars(self._width('notes'))),
            0 if per_year else _text_lines(territories[0], text_chars(self._width('territory'))),
            max((_text_lines(str(extra.get(key, '')), text_chars(self._width(key))) for key in extra_keys), default=0),
        )
        year_height = max(ROW_HEIGHT, math.ceil(TAG_MIN_HEIGHT / len(offers)))
        overflow = needed_lines * TEXT_LINE_HEIGHT + 4 - len(offers) * year_height
        end = last_year + 1 if overflow > 0 else last_year

        premiums = {v: [self._format_premium(o, v) for o in offers] for v in variants}
        for i, offer in enumerate(offers):
            r = start + i
            ws[f'{cols["year"]}{r}'] = f'{offer.insurance_year} год'
            ws[f'{cols["year"]}{r}'].alignment = center
            ws[f'{cols["sum"]}{r}'] = self._format_insurance_sum(offer)
            ws[f'{cols["sum"]}{r}'].number_format = MONEY
            ws[f'{cols["sum"]}{r}'].alignment = center
            for v in variants:
                premium = premiums[v][i]
                p_col, s_col = cols[f'premium_{v}'], cols['sum']
                if premium is not None:
                    franchise = self._format_franchise(offer, v)
                    ws[f'{cols[f"franchise_{v}"]}{r}'] = franchise if franchise is not None else 0
                    ws[f'{cols[f"rate_{v}"]}{r}'] = f'=IF(AND({s_col}{r}<>0,{p_col}{r}<>0),{p_col}{r}/{s_col}{r},"")'
                    ws[f'{p_col}{r}'] = premium
                    ws[f'{cols[f"payments_{v}"]}{r}'] = self._format_installment_payments(offer, v)
                ws[f'{cols[f"franchise_{v}"]}{r}'].number_format = MONEY
                ws[f'{cols[f"rate_{v}"]}{r}'].number_format = RATE
                ws[f'{p_col}{r}'].number_format = MONEY
                for key in ('franchise', 'rate', 'premium'):
                    ws[f'{cols[f"{key}_{v}"]}{r}'].alignment = center
                ws[f'{cols[f"payments_{v}"]}{r}'].alignment = center

        last_idx = ws[f'{cols["last"]}1'].column
        for r in range(start, end + 1):
            ws.row_dimensions[r].height = year_height if r <= last_year else overflow
            for c_idx in range(1, last_idx + 1):
                c = ws.cell(row=r, column=c_idx)
                c.font = detail
                c.border = Border(bottom=self.hair if r == end else None)
        # Тариф — главная цифра детализации: жирным и темнее остальных; ненулевая франшиза — красным полужирным,
        # чтобы клиент видел, что цена посчитана с франшизой (пожелание сотрудников 2026-10-15; ноль — как обычно)
        for v in variants:
            for r in range(start, last_year + 1):
                ws[f'{cols[f"rate_{v}"]}{r}'].font = _font(self.fs['detail'], bold=True)
                franchise_cell = ws[f'{cols[f"franchise_{v}"]}{r}']
                if franchise_cell.value:
                    franchise_cell.font = _font(self.fs['detail'], bold=True, color=self.palette['franchise'])

        # Компания и ценники — на весь блок, вместе с добавочной строкой: общая заливка; значение у верхнего края
        # блока — название видно сразу при прокрутке с закреплёнными строками (отзыв сотрудников 2026-10-14)
        self._merge_block(ws, cols['company'], start, end, name,
                          _font(self.fs['company'], bold=True), Alignment(vertical='top', wrap_text=True, indent=1))
        white = Side(style='thick', color='FFFFFF')
        for v in variants:
            letter = cols[f'total_{v}']
            p_col = cols[f'premium_{v}']
            value = f'=SUM({p_col}{start}:{p_col}{last_year})' if any(p is not None for p in premiums[v]) else None
            self._merge_block(ws, letter, start, end, value,
                              _font(self.fs['total'], bold=True, color=self.palette['header' if v == 1 else 'header_2']),
                              Alignment(horizontal='center', vertical='top'), MONEY)
            for r in range(start, end + 1):
                ws[f'{letter}{r}'].fill = self._fill('tag' if v == 1 else 'tag_2')
                ws[f'{letter}{r}'].border = Border(left=white, right=white, top=white, bottom=white)

        text = _font(self.fs['text'])
        top_left = Alignment(vertical='top', wrap_text=True)
        if not per_year:
            self._merge_block(ws, cols['territory'], start, end, territories[0], text, top_left)
        else:  # разные территории по годам — построчно, чтобы различия не потерялись
            for i, value in enumerate(territories):
                r = start + i
                c = ws[f'{cols["territory"]}{r}']
                c.value, c.font, c.alignment = value, text, top_left
                lines = _text_lines(value, text_chars(self._width('territory')))
                ws.row_dimensions[r].height = max(year_height, lines * TEXT_LINE_HEIGHT + 4)
        for key in extra_keys:
            value = extra.get(key, self.NO_DATA)
            is_amount = isinstance(value, Decimal)
            self._merge_block(
                ws, cols[key], start, end, value,
                _font(9, color=MUTED if value == self.NO_DATA else INK),
                Alignment(horizontal='center', vertical='top', wrap_text=True),
                MONEY if is_amount else None,
            )
        self._merge_block(ws, cols['notes'], start, end, notes, text, top_left)

        # Подсветка выбранной СК (и выбранного предложения) по ручным полям
        company_cell, variant_cell = self.selection_cells(cols)
        company_ref = '$' + re.sub(r'(\d+)', r'$\1', company_cell)
        variant_ref = '$' + re.sub(r'(\d+)', r'$\1', variant_cell)
        quoted = name.replace('"', '""')
        for v in variants:
            chosen = f'AND({company_ref}="{quoted}",{variant_ref}="Предложение {v}")'
            letter = cols[f'total_{v}']
            ws.conditional_formatting.add(f'{letter}{start}:{letter}{end}', FormulaRule(
                formula=[chosen], fill=self._fill('chosen_total'), stopIfTrue=True))
            ws.conditional_formatting.add(
                f'{cols[f"franchise_{v}"]}{start}:{cols[f"payments_{v}"]}{last_year}',
                FormulaRule(formula=[chosen], fill=self._fill('chosen_variant'), stopIfTrue=True))
        is_chosen = [f'{company_ref}="{quoted}"']
        ws.conditional_formatting.add(f'A{start}:A{end}', FormulaRule(formula=is_chosen, fill=self._fill('chosen_company')))
        ws.conditional_formatting.add(f'{cols["year"]}{start}:{cols["last"]}{end}',
                                      FormulaRule(formula=is_chosen, fill=self._fill('chosen')))
        return end

    def _block_territories(self, offers) -> List[str]:
        values = [self._get_export_coverage_territory(o) for o in offers]
        placeholders = {self.MISSING_COVERAGE_TERRITORY, self.LEGACY_COVERAGE_TERRITORY}
        texts = {}
        for value in values:
            if value not in placeholders:
                texts.setdefault(' '.join(value.split()).casefold(), value)
        if len(texts) > 1:
            return [self.LEGACY_TERRITORY_V2 if v == self.LEGACY_COVERAGE_TERRITORY else v for v in values]
        if texts:
            return [next(iter(texts.values()))]
        if self.MISSING_COVERAGE_TERRITORY in values:
            return [self.MISSING_COVERAGE_TERRITORY]
        return [self.LEGACY_TERRITORY_V2]

    def _merge_block(self, ws, letter, start, end, value, font, alignment, number_format=None) -> None:
        if end > start:
            ws.merge_cells(f'{letter}{start}:{letter}{end}')
        cell = ws[f'{letter}{start}']
        cell.value = value
        cell.font = font
        cell.alignment = alignment
        if number_format:
            cell.number_format = number_format

    def _write_declined_row(self, ws, row, name, cols) -> None:
        muted = _font(10, italic=True, color=MUTED)
        for c_idx in range(1, ws[f'{cols["last"]}1'].column + 1):
            c = ws.cell(row=row, column=c_idx)
            c.border = Border(bottom=self.hair)
            c.font = muted
        ws[f'A{row}'] = name
        ws[f'A{row}'].font = _font(11, bold=True, color=MUTED)
        ws[f'A{row}'].alignment = Alignment(vertical='center', indent=1)
        ws.merge_cells(f'{cols["total_1"]}{row}:{cols["numbers_last"]}{row}')
        ws[f'{cols["total_1"]}{row}'] = self.DECLINED_TEXT
        ws[f'{cols["total_1"]}{row}'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[row].height = DECLINED_ROW_HEIGHT

    def _apply_table_style(self, ws, cols, blocks, company_count, has_variant_2) -> None:
        """Вид таблицы: сетка, плотная линия между СК, рамка, заливка шапки и зебра по СК.

        Цвета: индиго — предложение 1, бирюза — предложение 2, терракота — условия (шапка блока
        территория…комментарии и колонки «Франшиза»).
        """
        top, sub = FIRST_DATA_ROW - 2, FIRST_DATA_ROW - 1
        last_col = ws[f'{cols["last"]}1'].column
        last_row = blocks[-1][1] if blocks else sub
        pal = self.palette
        grid = Side(style='thin', color=pal['grid'])
        separator = Side(style='medium', color=pal['separator'])
        frame = Side(style='medium', color=pal['frame'])
        variants = [1, 2] if has_variant_2 else [1]
        col = lambda key: ws[f'{cols[key]}1'].column
        totals = {col(f'total_{v}') for v in variants}
        conditions = range(col('territory'), last_col + 1)
        franchises = {col(f'franchise_{v}') for v in variants}

        def has_fill(cell):
            return cell.fill is not None and cell.fill.fill_type == 'solid'

        # Шапка: светлая заливка; блок условий — терракотовый; подписи предложений остаются тёмными
        for r in (top, sub):
            for c in range(1, last_col + 1):
                cell = ws.cell(row=r, column=c)
                if r == sub and c in totals:
                    continue
                if c in conditions:
                    cell.fill = self._fill('cond_fill')
                    if cell.value:
                        cell.font = _font(cell.font.sz, bold=True, color=pal['cond'])
                else:
                    cell.fill = self._fill('header_fill')
        for v in variants:
            letter = cols[f'{self.DETAIL_KEYS[0]}_{v}']
            ws[f'{letter}{top}'].font = _font(self.fs['detail'], bold=True,
                                              color=pal['header' if v == 1 else 'header_2'])
        for c in franchises:
            ws.cell(row=sub, column=c).font = _font(self.fs['column'], bold=True, color=pal['cond'])

        # Зебра по СК (ценники и уже залитые ячейки не трогаем) и серый фон отказов
        for index, (first, last) in enumerate(blocks):
            declined = index >= company_count
            if not declined and index % 2 == 0:
                continue
            for r in range(first, last + 1):
                for c in range(1, last_col + 1):
                    cell = ws.cell(row=r, column=c)
                    if c in totals and not declined:
                        continue
                    if declined or not has_fill(cell):
                        cell.fill = self._fill('declined_fill' if declined else 'zebra')

        # Сетка, разделитель между СК, рамка. Добавочная строка блока (продолжение длинного текста)
        # в колонках цифр без горизонтальной линии над ней — читается как часть блока, а не пустая строка
        block_ends = {last for _, last in blocks}
        year_col, numbers_last = col('year'), col('numbers_last')
        # Тёмные вертикали между блоками: СК | ИТОГО | год+сумма | детализация П1 | П2 | территория |
        # ответы СК | комментарии (внутри блоков — тонкая сетка)
        group_starts = {col('total_1'), year_col, col('territory'), col('notes')}
        group_starts |= {col(f'{self.DETAIL_KEYS[0]}_{v}') for v in variants}
        extras = [key for key in self.EXTRA_TITLES if key in cols]
        if extras:
            group_starts.add(col(extras[0]))
        overflow_rows = {r for first, last in blocks[:company_count] for r in range(first + 1, last + 1)
                         if ws.cell(row=r, column=year_col).value in (None, '')}
        for r in range(top, last_row + 1):
            for c in range(1, last_col + 1):
                bottom = separator if r in block_ends or r == sub else grid
                top_side = frame if r == top else (separator if r - 1 in block_ends or r == FIRST_DATA_ROW else grid)
                if c <= numbers_last and r + 1 in overflow_rows:
                    bottom = None
                if c <= numbers_last and r in overflow_rows:
                    top_side = None
                left = frame if c == 1 else (separator if c in group_starts else grid)
                right = frame if c == last_col else (separator if c + 1 in group_starts else grid)
                ws.cell(row=r, column=c).border = Border(
                    left=left, right=right, top=top_side, bottom=frame if r == last_row else bottom)

    @staticmethod
    def _setup_print(ws, cols) -> None:
        """Мягкая подготовка к печати: только стандартные параметры, которые менеджер видит и меняет
        в окне печати. Вся таблица — в ширину одного листа, по высоте — сколько получится."""
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.orientation = 'landscape'
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0  # 0 — «автоматически»: столько листов в высоту, сколько нужно
        # поля «Узкие» — как одноимённый пункт списка полей в Excel
        ws.page_margins.left = ws.page_margins.right = 0.25
        ws.page_margins.top = ws.page_margins.bottom = 0.75
        ws.page_margins.header = ws.page_margins.footer = 0.3
        ws.print_options.horizontalCentered = True
        ws.print_title_rows = f'{FIRST_DATA_ROW - 2}:{FIRST_DATA_ROW - 1}'  # шапка таблицы — на каждом листе
        ws.oddFooter.center.text = 'Стр. &P из &N'
        ws.oddFooter.center.size = 8

    def _write_transport_footnote(self, ws, row, cols) -> None:
        """Сноска к «ИТОГО*» — под таблицей, под колонками цифр."""
        ws.merge_cells(f'A{row}:{cols["numbers_last"]}{row}')
        cell = ws[f'A{row}']
        cell.value = self.TRANSPORT_FOOTNOTE
        cell.font = _font(9, italic=True, color=self.palette['title'])
        cell.alignment = Alignment(vertical='center', wrap_text=True)
        width = sum(self._width(k) for k in cols if k not in (*self.SERVICE_KEYS, 'territory', 'notes', *self.EXTRA_TITLES))
        ws.row_dimensions[row].height = _text_lines(self.TRANSPORT_FOOTNOTE, int(width * 1.1)) * 12 + 6

    # ── лист «Параметры запроса» ─────────────────────────────────────────────

    # Строки PDF-заявки, которые на листе «Параметры запроса» не нужны: наш сотрудник (white label)
    # и просьба к страховщику указать стоимость перевозки отдельно
    REQUEST_SHEET_SKIP = {'Менеджер сделки', 'Стоимость перевозки'}
    REQUEST_SHEET_LABELS = {'Страховая сумма': 'Тип страховой суммы'}  # «Неагрегатная» — тип, а не сумма

    def _request_sections(self, request) -> List[tuple]:
        """Все данные заявки для коллег лизинговой компании — из того же контекста, что PDF-заявка
        для страховщика (insurance_requests.application_export), чтобы лист и PDF не расходились.
        Пустые поля не выводятся; флаги параметров — явно «Да»/«Нет»."""
        from insurance_requests.application_export import build_application_context

        ctx = build_application_context(request)
        keep = lambda rows: [(self.REQUEST_SHEET_LABELS.get(label, label), value) for label, value in rows
                             if label not in self.REQUEST_SHEET_SKIP and str(value or '').strip()]
        strip = dict(ctx['strip'])

        title = ctx['object_title']
        brand = (request.object_brand or '').strip()
        kind = [part for part in ((request.machine_kind or '').strip(),
                                  f'марка {brand}' if brand and brand.lower() not in title.lower() else '') if part]
        object_name = ' · '.join([title, *kind])
        quantity = ctx['quantity_count']
        object_rows = [('Объект', object_name), *ctx['facts'],
                       ('Стоимость единицы' if quantity else 'Стоимость', ctx['cost'])]
        if quantity:
            object_rows += [('Количество', ctx['quantity_label']), ('Общая стоимость', ctx['cost_total'])]
        if ctx['legacy_note'] and not ctx['cost_known']:  # пометка нужна, только если данных объекта нет
            object_rows.append(('Примечание', ctx['legacy_note']))
        terms = list(ctx['terms_rows'])
        if not any(label == 'Уплата премии' for label, _ in terms):  # частота не распознана — хотя бы да/нет
            terms.append(('Рассрочка', self._get_installment_text_for_tech_info(request.has_installment)))

        parameters = [(item['label'], item['value']) for row in ctx['tile_rows'] for item in row if item]
        parameters += list(ctx['long_rows'])

        return [(title, rows) for title, rows in (
            ('Заявка', keep([
                ('Номер ДФА', strip.get('Номер ДФА')),
                ('Филиал', strip.get('Филиал')),
                ('Дата подачи', strip.get('Дата подачи')),
                ('Объект в партии', ctx['batch_label']),
                ('Менеджер лизинговой компании', request.manager_name),
            ])),
            ('Лизингополучатель', keep(ctx['insured_rows'])),
            ('Предмет лизинга', keep(object_rows)),
            ('Условия страхования', keep([
                *terms,
                ('Запрашиваемые риски', self._get_insurance_description_for_tech_info(request)),
            ])),
            ('Параметры и риски', keep(parameters)),
        ) if rows]

    def _build_request_sheet(self, ws, request) -> None:
        ws.sheet_view.showGridLines = False
        ws.column_dimensions['A'].width = 30
        ws.column_dimensions['B'].width = 80
        ws.merge_cells('A1:B1')
        ws['A1'] = 'Параметры, по которым делался запрос'
        ws['A1'].font = _font(13, bold=True, color=self.palette['title'])
        ws.row_dimensions[1].height = 24

        row = 3
        for title, items in self._request_sections(request):
            ws.merge_cells(f'A{row}:B{row}')
            ws[f'A{row}'] = title
            ws[f'A{row}'].font = _font(10, bold=True, color=self.palette['title'])
            for col in 'AB':
                ws[f'{col}{row}'].fill = self._fill('section')
                ws[f'{col}{row}'].border = Border(bottom=self.block_line)
            ws.row_dimensions[row].height = 20
            row += 1
            for label, value in items:
                text = self._sanitize_excel_text(value) or '—'
                ws[f'A{row}'] = label
                ws[f'A{row}'].font = _font(10, color=MUTED)
                ws[f'A{row}'].alignment = Alignment(vertical='top', wrap_text=True)
                ws[f'B{row}'] = text
                ws[f'B{row}'].font = _font(10)
                ws[f'B{row}'].alignment = Alignment(vertical='top', wrap_text=True)
                for col in 'AB':
                    ws[f'{col}{row}'].border = Border(bottom=self.hair)
                ws.row_dimensions[row].height = max(16, _text_lines(text, 90) * 14 + 3)
                row += 1
            row += 1



def build_filename(summary: InsuranceSummary, is_client_version: bool) -> str:
    digits = re.sub(r'[^\d]', '', summary.request.dfa_number or '') or str(summary.pk)
    prefix = 'client_svod_v2' if is_client_version else 'full_svod_v2'
    return f'{prefix}_{digits}_{date.today():%d_%m_%Y}.xlsx'
