"""Свод котировок V2 (бета, только суперпользователь).

Содержание то же, что у текущего свода (ExcelExportService + шаблоны templates/*summary*.xlsx):
лист «Свод» уходит клиенту, полная версия добавляет лист «Параметры запроса» для коллег
из лизинговой компании. Отличия — только в подаче (решения владельца 2026-10-04):

- white label: ни бренда, ни контактов, ни аналитики; палитра «деловой синий»;
- СК отсортированы по ИТОГО предложения 1, строки по годам как раньше;
- «Выбрана СК» / «Выбрано предложение» — ручные жёлтые поля, но с выпадающими списками;
  выбранная СК подсвечивается условным форматированием;
- подписи «Предложение 1/2» с размером франшизы, понятные заголовки колонок;
- вместо служебной «Нет данных: территория ранее не собиралась» — «—»;
- дата свода в шапке; в тех. листе добавлены срок лизинга, страхователь, противоугонные
  системы, тип страховой суммы и условия охраны.

Печать (A4): первая страница — всё от «Страховой компании» до последнего «ИТОГО» в одном
масштабе (ориентация — та, где цифры влезают на один лист крупнее); территория и комментарии — ручным разрывом на следующую
страницу, с повтором колонки СК. Если строк больше, чем помещается, разрывы ставятся
только между блоками СК — компания не разрезается.

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
from openpyxl.worksheet.pagebreak import Break

from ..models import InsuranceSummary
from .excel_services import ExcelExportService, ExcelExportServiceError

logger = logging.getLogger(__name__)

FONT = 'Arial'
INK = '1F2328'
MUTED = '6B7280'
INPUT_FILL = PatternFill('solid', fgColor='FFF2B3')  # ручные поля менеджера — всегда жёлтые

# Палитра white label (без фирменных цветов брокера), выбор владельца 2026-10-05 — «деловой синий».
# header/header_2 — шапки предложений 1/2, sub/sub_2 — их подзаголовки, total_* — выделение
# колонок «ИТОГО», accent — линия под заголовком. Другие варианты (графит, изумруд, синий
# с золотом) рассматривались и отклонены; новую палитру достаточно добавить сюда.
PALETTES = {
    'navy': {
        'title': '1B3A6B', 'accent': '2E6BC6', 'header': '1B3A6B', 'header_2': '2E5C99',
        'sub': 'DCE6F2', 'sub_2': 'E2EBF6', 'band': 'F5F8FC', 'hair': 'D5DEEA', 'block': '8FA9CC',
        'company': '1B3A6B', 'total_fill': 'E6EFFB', 'total_text': '1B3A6B',
        'chosen': 'DCEBFB', 'chosen_variant': 'BCD5F5', 'section': 'E8EEF6',
    },
}
DEFAULT_PALETTE = 'navy'

MONEY = '#,##0'  # копейки хранятся в ячейке, на экране — целые рубли, как в своде V1
RATE = '0.00%'

FIRST_DATA_ROW = 10
LINE_HEIGHT = 12.5  # pt на строку текста шрифтом 9
MIN_ROW_HEIGHT = 18

# Печать: A4 (pt), поля в дюймах
A4_SHORT, A4_LONG = 595.3, 841.9
MARGIN_LR, MARGIN_TB = 0.4, 0.5
PAGE_SIZES = {'landscape': (A4_LONG, A4_SHORT), 'portrait': (A4_SHORT, A4_LONG)}
# Цифры на одном листе, пока шрифт 9 pt на бумаге не мельче ~6.5 pt; иначе — по блокам на несколько
ONE_PAGE_MIN_SCALE = 0.72


def _font(size=9, bold=False, italic=False, color=INK):
    return Font(name=FONT, size=size, bold=bold, italic=italic, color=color)


def _text_lines(text, chars_per_line: int) -> int:
    if not text:
        return 0
    return sum(max(1, math.ceil(len(part) / chars_per_line)) for part in str(text).split('\n'))


def col_points(width: float) -> float:
    """Ширина колонки Excel (в символах) в pt: px = width*7+5 при 96 dpi."""
    return int(width * 7 + 5) * 0.75


class SummaryExportV2Service(ExcelExportService):
    """Генерация свода V2 с нуля, без xlsx-шаблона."""

    LEGACY_TERRITORY_V2 = '—'

    WIDTHS = {'company': 20, 'year': 8, 'sum': 15, 'rate': 9, 'premium': 13, 'franchise': 12,
              'payments': 10, 'total': 14, 'territory': 32, 'notes': 64}

    def __init__(self, palette: str = DEFAULT_PALETTE):
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
            output.seek(0)
            return output
        except ExcelExportServiceError:
            raise
        except Exception as e:
            logger.error(f"Ошибка генерации свода V2 для свода ID {summary.id}: {e}", exc_info=True)
            raise ExcelExportServiceError(f"Ошибка при генерации свода V2: {e}") from e

    # ── колонки ──────────────────────────────────────────────────────────────

    @staticmethod
    def columns(has_variant_2: bool) -> Dict[str, str]:
        keys = ['company', 'year', 'sum']
        for v in ([1, 2] if has_variant_2 else [1]):
            keys += [f'rate_{v}', f'premium_{v}', f'franchise_{v}', f'payments_{v}', f'total_{v}']
        cols = {key: get_column_letter(i) for i, key in enumerate(keys, start=1)}
        cols['numbers_last'] = get_column_letter(len(keys))  # последняя колонка «ИТОГО»
        cols['territory'] = get_column_letter(len(keys) + 1)
        cols['notes'] = cols['last'] = get_column_letter(len(keys) + 2)
        return cols

    def _fill(self, key: str):
        color = self.palette[key]
        return PatternFill('solid', fgColor=color) if color else None

    def _width(self, key: str) -> float:
        return self.WIDTHS[re.sub(r'_\d$', '', key)]

    # ── лист «Свод» ──────────────────────────────────────────────────────────

    def _build_summary_sheet(self, ws, summary: InsuranceSummary, has_variant_2: bool) -> None:
        cols = self.columns(has_variant_2)
        for key, letter in cols.items():
            if key not in ('numbers_last', 'last'):
                ws.column_dimensions[letter].width = self._width(key)
        ws.sheet_view.showGridLines = False

        companies = self._sorted_companies(summary)
        declined = self._get_declined_companies(summary)

        self._build_header(ws, summary, cols, [name for name, _ in companies], has_variant_2)
        self._build_table_header(ws, cols, companies, has_variant_2)

        row = FIRST_DATA_ROW
        blocks: List[Tuple[int, int]] = []
        asset_note = self._get_additional_note_for_asset_status(summary)
        for index, (name, offers) in enumerate(companies):
            end = self._write_company_block(ws, row, name, offers, cols, has_variant_2, asset_note,
                                            banded=index % 2 == 1)
            blocks.append((row, end))
            row = end + 1
        for name in declined:
            self._write_declined_row(ws, row, name, cols)
            blocks.append((row, row))
            row += 1

        self._setup_print(ws, cols, blocks, max(row - 1, FIRST_DATA_ROW))

    def _sorted_companies(self, summary: InsuranceSummary) -> List[tuple]:
        companies = self._validate_companies_data(self._get_companies_sorted_data(summary))

        def key(item):
            name, offers = item
            total = self._calculate_premium_sum(offers, 1)
            return (total is None, total or Decimal('0'), name)

        return sorted(companies.items(), key=key)

    @staticmethod
    def selection_cells(cols) -> Tuple[str, str]:
        """Ручные жёлтые поля «Выбрана СК» и «Выбрано предложение» — справа, для менеджера
        (при печати попадают на страницу с территорией и комментариями)."""
        return f'{cols["notes"]}2', f'{cols["notes"]}4'

    def _build_header(self, ws, summary, cols, company_names, has_variant_2) -> None:
        request = summary.request
        value_end = cols['total_1']

        ws.merge_cells(f'A1:{value_end}1')
        cell = ws['A1']
        cell.value = f'Свод котировок и условий от {timezone.localdate():%d.%m.%Y}'
        cell.font = _font(14, bold=True, color=self.palette['title'])
        cell.alignment = Alignment(vertical='center')
        ws.row_dimensions[1].height = 26
        if self.palette['accent']:
            accent = Side(style='thick', color=self.palette['accent'])
            for idx in range(1, ws[f'{value_end}1'].column + 1):
                ws.cell(row=1, column=idx).border = Border(bottom=accent)

        object_text = request.object_summary or ''
        year = (request.manufacturing_year or '').strip()
        if year and year not in object_text and f'{year} г.' not in object_text:
            object_text = f'{object_text}, {year}' if object_text else year

        rows = [
            ('Заявка №', request.dfa_number),
            ('Объект страхования', object_text),
            ('Лизингополучатель', request.client_name),
            ('Цели использования', request.usage_purposes or ''),
            ('Примечание', summary.notes or ''),
        ]
        value_keys = [k for k in cols if k not in ('company', 'year', 'numbers_last', 'territory', 'notes', 'last')]
        chars = int(sum(self._width(k) for k in value_keys) * 1.05)
        for offset, (label, value) in enumerate(rows):
            r = 2 + offset
            ws.merge_cells(f'A{r}:B{r}')
            ws[f'A{r}'].value = label
            ws[f'A{r}'].font = _font(9, color=MUTED)
            ws[f'A{r}'].alignment = Alignment(vertical='top')
            ws.merge_cells(f'C{r}:{value_end}{r}')
            ws[f'C{r}'].value = self._sanitize_excel_text(value)
            ws[f'C{r}'].font = _font(10, bold=label in ('Заявка №', 'Объект страхования'))
            ws[f'C{r}'].alignment = Alignment(vertical='top', wrap_text=True)
            ws.row_dimensions[r].height = max(16, _text_lines(ws[f'C{r}'].value, chars) * 14)

        # Ручные поля выбора справа: подпись в колонке территории, жёлтое поле — в комментариях
        company_cell, variant_cell = self.selection_cells(cols)
        for coord, label in ((company_cell, 'Выбрана СК:'), (variant_cell, 'Выбрано предложение:')):
            row = ws[coord].row
            label_cell = ws[f'{cols["territory"]}{row}']
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
        ws.row_dimensions[top].height = 20
        ws.row_dimensions[sub].height = 26
        white = _font(9, bold=True, color='FFFFFF')
        center = Alignment(horizontal='center', vertical='center', wrap_text=True)

        def style(letter, row, fill, font):
            c = ws[f'{letter}{row}']
            c.fill, c.font, c.alignment, c.border = fill, font, center, self.cell_border

        for key, title in (('company', 'Страховая компания'), ('year', 'Год'),
                           ('sum', 'Страховая сумма'), ('territory', 'Территория страхования'),
                           ('notes', 'Комментарии')):
            letter = cols[key]
            ws.merge_cells(f'{letter}{top}:{letter}{sub}')
            style(letter, top, self._fill('header'), white)
            style(letter, sub, self._fill('header'), white)
            ws[f'{letter}{top}'].value = title

        for v in ([1, 2] if has_variant_2 else [1]):
            first, last = cols[f'rate_{v}'], cols[f'total_{v}']
            ws.merge_cells(f'{first}{top}:{last}{top}')
            for idx in range(ws[f'{first}{top}'].column, ws[f'{last}{top}'].column + 1):
                style(get_column_letter(idx), top, self._fill('header' if v == 1 else 'header_2'), white)
            ws[f'{first}{top}'].value = self._variant_caption(companies, v)
            for key, title in (('rate', 'Тариф'), ('premium', 'Премия'), ('franchise', 'Франшиза'),
                               ('payments', 'Платежей в год'), ('total', 'ИТОГО за срок')):
                letter = cols[f'{key}_{v}']
                style(letter, sub, self._fill('sub' if v == 1 else 'sub_2'),
                      _font(9, bold=True, color=self.palette['title']))
                ws[f'{letter}{sub}'].value = title

    def _write_company_block(self, ws, start, name, offers, cols, has_variant_2, asset_note, banded) -> int:
        """Блок СК: строки по годам; возвращает номер последней строки блока."""
        offers = sorted(offers, key=lambda o: o.insurance_year)
        end = start + len(offers) - 1
        variants = [1, 2] if has_variant_2 else [1]
        right = Alignment(horizontal='right', vertical='center')
        center = Alignment(horizontal='center', vertical='center')

        premiums = {v: [self._format_premium(o, v) for o in offers] for v in variants}
        for i, offer in enumerate(offers):
            r = start + i
            ws[f'{cols["year"]}{r}'] = f'{offer.insurance_year} год'
            ws[f'{cols["year"]}{r}'].alignment = center
            ws[f'{cols["sum"]}{r}'] = self._format_insurance_sum(offer)
            ws[f'{cols["sum"]}{r}'].number_format = MONEY
            ws[f'{cols["sum"]}{r}'].alignment = right
            for v in variants:
                premium = premiums[v][i]
                p_col, s_col = cols[f'premium_{v}'], cols['sum']
                if premium is not None:
                    ws[f'{cols[f"rate_{v}"]}{r}'] = f'=IF(AND({s_col}{r}<>0,{p_col}{r}<>0),{p_col}{r}/{s_col}{r},"")'
                    ws[f'{p_col}{r}'] = premium
                    franchise = self._format_franchise(offer, v)
                    ws[f'{cols[f"franchise_{v}"]}{r}'] = franchise if franchise is not None else 0
                    ws[f'{cols[f"payments_{v}"]}{r}'] = self._format_installment_payments(offer, v)
                ws[f'{cols[f"rate_{v}"]}{r}'].number_format = RATE
                ws[f'{p_col}{r}'].number_format = MONEY
                ws[f'{cols[f"franchise_{v}"]}{r}'].number_format = MONEY
                for key in ('rate', 'premium', 'franchise'):
                    ws[f'{cols[f"{key}_{v}"]}{r}'].alignment = right
                ws[f'{cols[f"payments_{v}"]}{r}'].alignment = center

        # Объединённые по блоку: компания, ИТОГО, территория, комментарии
        self._merge_block(ws, cols['company'], start, end, name,
                          _font(10, bold=True, color=self.palette['company']),
                          Alignment(vertical='center', wrap_text=True))
        for v in variants:
            p_col = cols[f'premium_{v}']
            value = f'=SUM({p_col}{start}:{p_col}{end})' if any(p is not None for p in premiums[v]) else None
            self._merge_block(ws, cols[f'total_{v}'], start, end, value,
                              _font(11, bold=True, color=self.palette['total_text']), right, MONEY)

        territories = self._block_territories(offers)
        if len(territories) == 1:
            self._merge_block(ws, cols['territory'], start, end, territories[0], _font(9),
                              Alignment(vertical='top', wrap_text=True))
        else:  # разные территории по годам — построчно, чтобы различия не потерялись
            for i, text in enumerate(territories):
                c = ws[f'{cols["territory"]}{start + i}']
                c.value, c.font, c.alignment = text, _font(9), Alignment(vertical='top', wrap_text=True)

        additional = self._combine_additional_notes(
            asset_note, self._get_franchise_approval_note_for_company(offers, name)
        )
        notes = self._consolidate_notes(offers, additional) or ''
        self._merge_block(ws, cols['notes'], start, end, notes, _font(9),
                          Alignment(vertical='top', wrap_text=True))

        last_idx = ws[f'{cols["last"]}1'].column
        for r in range(start, end + 1):
            for c_idx in range(1, last_idx + 1):
                c = ws.cell(row=r, column=c_idx)
                if c.font is None or c.font.name != FONT:
                    c.font = _font(9)
                c.border = Border(left=self.hair, right=self.hair, top=self.hair,
                                  bottom=self.block_line if r == end else self.hair)
                if banded:
                    c.fill = self._fill('band')
        if self.palette['total_fill']:
            for v in variants:
                for r in range(start, end + 1):
                    ws[f'{cols[f"total_{v}"]}{r}'].fill = self._fill('total_fill')

        # Высота строк: чтобы текст территории и комментариев не обрезался
        needed_lines = max(
            _text_lines(notes, int(self._width('notes') * 1.15)),
            max((_text_lines(t, int(self._width('territory') * 1.15)) for t in territories), default=0),
        )
        per_row = max(MIN_ROW_HEIGHT, needed_lines * LINE_HEIGHT / len(offers) + 2)
        for r in range(start, end + 1):
            ws.row_dimensions[r].height = per_row

        # Подсветка выбранной СК (и выбранного предложения) по ручным полям
        company_cell, variant_cell = self.selection_cells(cols)
        company_ref = '$' + re.sub(r'(\d+)', r'$\1', company_cell)
        variant_ref = '$' + re.sub(r'(\d+)', r'$\1', variant_cell)
        quoted = name.replace('"', '""')
        ws.conditional_formatting.add(f'A{start}:{cols["last"]}{end}',
                                      FormulaRule(formula=[f'{company_ref}="{quoted}"'], fill=self._fill('chosen')))
        for v in variants:
            ws.conditional_formatting.add(
                f'{cols[f"rate_{v}"]}{start}:{cols[f"total_{v}"]}{end}',
                FormulaRule(formula=[f'AND({company_ref}="{quoted}",{variant_ref}="Предложение {v}")'],
                            fill=self._fill('chosen_variant'), stopIfTrue=True))
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
        muted = _font(9, italic=True, color=MUTED)
        for c_idx in range(1, ws[f'{cols["last"]}1'].column + 1):
            c = ws.cell(row=row, column=c_idx)
            c.border = Border(left=self.hair, right=self.hair, top=self.hair, bottom=self.block_line)
            c.font = muted
        ws[f'A{row}'] = name
        ws[f'A{row}'].font = _font(10, bold=True, color=MUTED)
        ws.merge_cells(f'{cols["year"]}{row}:{cols["numbers_last"]}{row}')
        ws[f'{cols["year"]}{row}'] = self.DECLINED_TEXT
        ws[f'{cols["year"]}{row}'].alignment = Alignment(horizontal='center', vertical='center')
        ws.row_dimensions[row].height = MIN_ROW_HEIGHT

    # ── печать ───────────────────────────────────────────────────────────────

    @staticmethod
    def _span_points(ws, first_col: int, last_col: int) -> float:
        return sum(col_points(ws.column_dimensions[get_column_letter(i)].width or 8.43)
                   for i in range(first_col, last_col + 1))

    def print_plan(self, ws, cols, blocks: List[Tuple[int, int]], last_row: int) -> Dict:
        """Ориентация, масштаб и разрывы: цифры на одном листе, если это читаемо; блоки СК не режутся."""
        plans = [self._plan_for(ws, cols, blocks, last_row, o) for o in ('landscape', 'portrait')]
        # меньше страниц с цифрами, затем крупнее; при равенстве — альбомная (первая)
        return min(plans, key=lambda p: (p['pages_down'], -p['scale']))

    def _plan_for(self, ws, cols, blocks, last_row: int, orientation: str) -> Dict:
        page_width, page_height_pt = PAGE_SIZES[orientation]
        printable_width = page_width - 2 * MARGIN_LR * 72
        printable_height = page_height_pt - 2 * MARGIN_TB * 72
        col = lambda key: ws[f'{cols[key]}1'].column
        numbers_width = self._span_points(ws, 1, col('numbers_last'))
        # Вторая страница по ширине: повторяемая колонка СК + территория + комментарии
        conditions_width = self._span_points(ws, 1, 1) + self._span_points(ws, col('territory'), col('notes'))
        width_scale = min(1.0, printable_width / numbers_width, printable_width / conditions_width)

        height = lambda first, last: sum(ws.row_dimensions[r].height or 15 for r in range(first, last + 1))
        total_height = height(1, last_row)
        one_page_scale = min(width_scale, printable_height / total_height)
        if one_page_scale >= ONE_PAGE_MIN_SCALE:
            return {'orientation': orientation, 'scale': one_page_scale, 'row_breaks': [], 'pages_down': 1}

        # Не помещается на один лист читаемо: масштаб по ширине, переносы между блоками СК
        page_height = printable_height / width_scale
        titles_height = height(FIRST_DATA_ROW - 2, FIRST_DATA_ROW - 1)
        used = height(1, FIRST_DATA_ROW - 1)
        breaks = []
        for first, last in blocks:
            block_height = height(first, last)
            if used + block_height > page_height and used > titles_height:
                breaks.append(first - 1)
                used = titles_height
            used += block_height
        return {'orientation': orientation, 'scale': width_scale, 'row_breaks': breaks,
                'pages_down': len(breaks) + 1}

    def _setup_print(self, ws, cols, blocks, last_row: int) -> None:
        ws.freeze_panes = f'A{FIRST_DATA_ROW}'
        ws.print_area = f'A1:{cols["last"]}{last_row}'
        ws.print_title_rows = f'{FIRST_DATA_ROW - 2}:{FIRST_DATA_ROW - 1}'
        ws.print_title_cols = 'A:A'  # название СК — и на странице с территорией/комментариями
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.pageOrder = 'downThenOver'  # сначала все цифры, потом условия
        ws.page_margins.left = ws.page_margins.right = MARGIN_LR
        ws.page_margins.top = ws.page_margins.bottom = MARGIN_TB
        ws.page_margins.header = ws.page_margins.footer = 0.25
        ws.oddFooter.center.text = 'Стр. &P из &N'
        ws.oddFooter.center.size = 8

        plan = self.print_plan(ws, cols, blocks, last_row)
        ws.page_setup.orientation = plan['orientation']
        # Явный масштаб вместо «вписать»: при «вписать» Excel игнорирует ручные разрывы
        ws.sheet_properties.pageSetUpPr.fitToPage = False
        ws.page_setup.scale = max(10, math.floor(plan['scale'] * 100))
        ws.col_breaks.append(Break(id=ws[f'{cols["numbers_last"]}1'].column))
        for row in plan['row_breaks']:
            ws.row_breaks.append(Break(id=row))

    # ── лист «Параметры запроса» ─────────────────────────────────────────────

    def _request_sections(self, request) -> List[tuple]:
        franchise = self._get_franchise_text_for_tech_info(request.franchise_type or 'none')
        if request.franchise_type != 'none' and request.franchise_amount_display:
            franchise = f'{franchise}; размер франшизы: {request.franchise_amount_display}'

        conditions = [
            ('Тип страхования', request.get_insurance_type_display()),
            ('Предмет лизинга', request.object_summary),
            ('Срок договора лизинга', request.lease_term_display),
            ('Страхователь', request.get_insured_party_display() if request.insured_party else ''),
            ('Банк-кредитор', request.creditor_bank),
            ('Франшиза', franchise),
            ('Рассрочка', self._get_installment_text_for_tech_info(request.has_installment)),
            ('Цели использования', request.usage_purposes),
            ('Запрашиваемые риски', self._get_insurance_description_for_tech_info(request)),
        ]
        sections = [
            ('Данные о клиенте', [
                ('Заявка', request.dfa_number), ('Лизингополучатель', request.client_name),
                ('ИНН', request.inn), ('Филиал', request.branch),
            ]),
            ('Условия запроса', conditions),
        ]
        if request.insurance_type in ('КАСКО', 'страхование спецтехники'):
            sections.append(('Доп. параметры КАСКО / спецтехники', [
                ('Автозапуск', self._get_autostart_text_for_tech_info(request.has_autostart)),
                ('Комплектность ключей', request.key_completeness),
                ('ПТС / ПСМ', request.pts_psm),
                ('Телематический комплекс', request.telematics_complex),
                ('Противоугонные системы', request.anti_theft_systems),
            ]))
        if request.insurance_type == 'страхование имущества':
            sections.append(('Доп. параметры имущества', [
                ('Территория по исходной заявке', request.insurance_territory),
                ('Перевозка', 'Запрос с условием перевозки' if request.has_transportation else ''),
                ('СМР', 'Запрос с условием СМР' if request.has_construction_work else ''),
                ('Тип страховой суммы',
                 request.get_insured_sum_type_display() if request.insured_sum_type else ''),
                ('Условия охраны / хранения', request.guard_conditions),
            ]))
        return sections

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
                ws[f'A{row}'].font = _font(9, color=MUTED)
                ws[f'A{row}'].alignment = Alignment(vertical='top', wrap_text=True)
                ws[f'B{row}'] = text
                ws[f'B{row}'].font = _font(9)
                ws[f'B{row}'].alignment = Alignment(vertical='top', wrap_text=True)
                for col in 'AB':
                    ws[f'{col}{row}'].border = Border(bottom=self.hair)
                ws.row_dimensions[row].height = max(16, _text_lines(text, 90) * LINE_HEIGHT + 3)
                row += 1
            row += 1

        ws.page_setup.orientation = 'portrait'
        ws.page_setup.paperSize = ws.PAPERSIZE_A4
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr.fitToPage = True
        ws.page_margins.left = ws.page_margins.right = MARGIN_LR
        ws.print_area = f'A1:B{row}'


def build_filename(summary: InsuranceSummary, is_client_version: bool) -> str:
    digits = re.sub(r'[^\d]', '', summary.request.dfa_number or '') or str(summary.pk)
    prefix = 'client_svod_v2' if is_client_version else 'full_svod_v2'
    return f'{prefix}_{digits}_{date.today():%d_%m_%Y}.xlsx'
