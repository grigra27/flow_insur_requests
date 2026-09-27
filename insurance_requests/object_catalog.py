"""Справочник техники: марка, класс объекта и вид машины по описанию объекта заявки.

docs/improvement_plans/tariffs_analytics_2026_09.md, шаг 1. Поле `brand` заявки ненадёжно (парсер
кладёт туда первое слово описания: «седельный», «Гусеничный»), а в полном описании марка есть почти
всегда. Модуль не зависит от моделей и базы — используется при сохранении заявки, в миграции данных и
в команде пересчёта `classify_objects`.

`classify(text, insurance_type, dfa_number)` → ObjectInfo(brand, object_class, machine_kind):
- brand — каноническое название марки или '' (не узнана);
- object_class — один из OBJECT_CLASSES;
- machine_kind — вид машины для спецтехники (экскаватор, кран…) или ''.

Словарь пополняется по мере появления новых марок: после правки — `python manage.py classify_objects --apply`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

PASSENGER = 'passenger'
LCV = 'lcv'
TRUCK = 'truck'
TRAILER = 'trailer'
BUS = 'bus'
SPECIAL = 'special'
EQUIPMENT = 'equipment'
OTHER = 'other'

OBJECT_CLASSES = [
    (PASSENGER, 'Легковые'),
    (LCV, 'Лёгкие коммерческие'),
    (TRUCK, 'Грузовые и тягачи'),
    (TRAILER, 'Прицепы и полуприцепы'),
    (BUS, 'Автобусы'),
    (SPECIAL, 'Спецтехника'),
    (EQUIPMENT, 'Оборудование и имущество'),
    (OTHER, 'Прочее'),
]
OBJECT_CLASS_LABELS = dict(OBJECT_CLASSES)

# (каноническое название, варианты написания, класс по умолчанию). Варианты сравниваются без учёта
# регистра, целым словом. Класс по умолчанию уточняется ключевыми словами описания (тягач, прицеп…).
BRANDS: List[Tuple[str, Tuple[str, ...], str]] = [
    # отечественные
    ('ГАЗ', ('газель', 'gazelle', 'газели', 'соболь', 'sobol', 'газ', 'gaz', 'валдай'), LCV),
    ('ГАЗ', ('газон', 'садко', 'sadko'), TRUCK),
    ('КамАЗ', ('камаз', 'kamaz'), TRUCK),
    ('МАЗ', ('маз', 'maz'), TRUCK),
    ('Урал', ('урал', 'ural'), TRUCK),
    ('УАЗ', ('уаз', 'uaz'), PASSENGER),
    ('LADA', ('lada', 'лада', 'ваз', 'vaz'), PASSENGER),
    ('Evolute', ('evolute', 'эволют'), PASSENGER),
    ('Sollers', ('sollers', 'соллерс'), LCV),
    ('Tenet', ('tenet', 'тенет'), PASSENGER),
    ('Москвич', ('москвич', 'moskvich'), PASSENGER),
    ('НЕФАЗ', ('нефаз', 'nefaz'), BUS),
    ('ПАЗ', ('паз', 'paz'), BUS),
    ('ЛиАЗ', ('лиаз', 'liaz'), BUS),
    ('Тонар', ('тонар', 'tonar'), TRAILER),
    ('ГРАЗ', ('граз', 'graz'), TRAILER),
    ('Тверьстроймаш', ('tverstroymash', 'тверьстроймаш'), TRAILER),
    ('Сибирские Вездеходы', ('сибирские вездеходы',), SPECIAL),
    ('ЧЕТРА', ('четра', 'chetra'), SPECIAL),
    ('ДСТ-Урал', ('дст-урал',), SPECIAL),
    ('Ростсельмаш', ('ростсельмаш', 'рсм'), SPECIAL),
    ('Кировец', ('кировец', 'kirovets'), SPECIAL),
    ('МТЗ', ('мтз', 'беларус', 'belarus'), SPECIAL),
    # китайские легковые и LCV
    ('Haval', ('haval', 'хавал', 'хавейл'), PASSENGER),
    ('Great Wall', ('great wall', 'gwm', 'poer', 'wey'), PASSENGER),
    ('Tank', ('tank',), PASSENGER),
    ('Geely', ('geely', 'джили'), PASSENGER),
    ('Chery', ('chery', 'чери'), PASSENGER),
    ('Exeed', ('exeed', 'эксид'), PASSENGER),
    ('Omoda', ('omoda',), PASSENGER),
    ('Jaecoo', ('jaecoo',), PASSENGER),
    ('Jetour', ('jetour', 'джетур'), PASSENGER),
    ('Changan', ('changan', 'чанган'), PASSENGER),
    ('GAC', ('gac',), PASSENGER),
    ('Lynk & Co', ('lynk and co', 'lynk & co', 'lynk'), PASSENGER),
    ('Li Auto', ('li auto', 'lixiang', 'li l7', 'li l9'), PASSENGER),
    ('Zeekr', ('zeekr',), PASSENGER),
    ('Voyah', ('voyah',), PASSENGER),
    ('Avatr', ('avatr',), PASSENGER),
    ('Hongqi', ('hongqi',), PASSENGER),
    ('Knewstar', ('knewstar',), PASSENGER),
    ('BAIC', ('baic',), PASSENGER),
    ('Belgee', ('belgee',), PASSENGER),
    ('JAC', ('jac',), LCV),
    ('Foton', ('foton', 'фотон'), LCV),
    ('Dongfeng', ('dongfeng', 'донгфенг'), TRUCK),
    # китайские грузовые и автобусы
    ('Sitrak', ('sitrak', 'ситрак'), TRUCK),
    ('Shacman', ('shacman', 'шакман', 'shaanxi'), TRUCK),
    ('Howo', ('howo', 'хово', 'sinotruk'), TRUCK),
    ('FAW', ('faw', 'фав'), TRUCK),
    ('Beiben', ('beiben',), TRUCK),
    ('Yutong', ('yutong', 'ютонг'), BUS),
    ('Higer', ('higer',), BUS),
    ('Zhongtong', ('zhongtong',), BUS),
    # европейские, японские, американские, корейские
    ('Toyota', ('toyota', 'тойота'), PASSENGER),
    ('Lexus', ('lexus', 'лексус'), PASSENGER),
    ('BMW', ('bmw', 'бмв'), PASSENGER),
    ('Mercedes-Benz', ('mercedes-benz', 'mercedes', 'mercedec-benz', 'мерседес'), PASSENGER),
    ('Audi', ('audi', 'ауди'), PASSENGER),
    ('Porsche', ('porsche', 'порше'), PASSENGER),
    ('Land Rover', ('land rover', 'range rover'), PASSENGER),
    ('Volkswagen', ('volkswagen', 'фольксваген', 'vw'), PASSENGER),
    ('Skoda', ('skoda', 'шкода'), PASSENGER),
    ('Ford', ('ford', 'форд'), LCV),
    ('RAM', ('ram',), PASSENGER),
    ('GMC', ('gmc',), PASSENGER),
    ('Chevrolet', ('chevrolet', 'шевроле'), PASSENGER),
    ('Cadillac', ('cadillac',), PASSENGER),
    ('Mazda', ('mazda', 'мазда'), PASSENGER),
    ('Nissan', ('nissan', 'ниссан'), PASSENGER),
    ('Mitsubishi', ('mitsubishi', 'мицубиси'), PASSENGER),
    ('Kia', ('kia', 'киа'), PASSENGER),
    ('Hyundai', ('hyundai', 'хендай', 'хундай', 'хёндэ'), PASSENGER),
    ('Renault', ('renault', 'рено'), PASSENGER),
    ('MAN', ('man',), TRUCK),
    ('Scania', ('scania', 'скания'), TRUCK),
    ('Volvo', ('volvo', 'вольво'), TRUCK),
    ('DAF', ('daf',), TRUCK),
    ('Iveco', ('iveco', 'ивеко'), TRUCK),
    ('Isuzu', ('isuzu', 'исузу'), TRUCK),
    ('Hino', ('hino',), TRUCK),
    ('Fuso', ('fuso',), TRUCK),
    # прицепы
    ('Schmitz', ('schmitz', 'шмитц'), TRAILER),
    ('Krone', ('krone', 'кроне'), TRAILER),
    ('Kögel', ('kogel', 'kögel'), TRAILER),
    ('Kassbohrer', ('kassbohrer', 'kässbohrer'), TRAILER),
    ('Wielton', ('wielton',), TRAILER),
    ('Grunwald', ('grunwald', 'грюнвальд'), TRAILER),
    ('Chengli', ('chengli',), TRAILER),
    ('Fliegl', ('fliegl',), TRAILER),
    ('Сеспель', ('сеспель', 'sespel'), TRAILER),
    # спецтехника
    ('SANY', ('sany', 'сани'), SPECIAL),
    ('XCMG', ('xcmg',), SPECIAL),
    ('Zoomlion', ('zoomlion',), SPECIAL),
    ('LiuGong', ('liugong', 'лю гонг'), SPECIAL),
    ('Lovol', ('lovol',), SPECIAL),
    ('Shantui', ('shantui',), SPECIAL),
    ('SDLG', ('sdlg', 'lgce'), SPECIAL),
    ('XGMA', ('xgma',), SPECIAL),
    ('Sunward', ('sunward',), SPECIAL),
    ('Lonking', ('lonking',), SPECIAL),
    ('Heli', ('heli',), SPECIAL),
    ('NFLG', ('nflg',), SPECIAL),
    ('Caterpillar', ('caterpillar', 'cat'), SPECIAL),
    ('JCB', ('jcb',), SPECIAL),
    ('Komatsu', ('komatsu', 'комацу'), SPECIAL),
    ('Hitachi', ('hitachi',), SPECIAL),
    ('Doosan', ('doosan', 'develon'), SPECIAL),
    ('New Holland', ('new holland', 'holland'), SPECIAL),
    ('John Deere', ('john deere',), SPECIAL),
    ('Bobcat', ('bobcat',), SPECIAL),
    ('Liebherr', ('liebherr',), SPECIAL),
    ('Kubota', ('kubota',), SPECIAL),
    ('Case', ('case',), SPECIAL),
    ('Hidromek', ('hidromek',), SPECIAL),
    ('Wirtgen', ('wirtgen',), SPECIAL),
    ('Vögele', ('vogele', 'vögele'), SPECIAL),
    ('HAMM', ('hamm',), SPECIAL),
    ('Bomag', ('bomag',), SPECIAL),
    ('Dynapac', ('dynapac',), SPECIAL),
    ('BULL', ('bull',), SPECIAL),
    ('LS Tractor', ('ls',), SPECIAL),
    ('Manitou', ('manitou',), SPECIAL),
    ('Tadano', ('tadano',), SPECIAL),
    ('SMA', ('sma',), SPECIAL),
    ('Baltmotors', ('baltmotors',), SPECIAL),
    ('AODES', ('aodes',), SPECIAL),
    ('Leotrack', ('leotrack',), SPECIAL),
    ('TRF', ('trf',), SPECIAL),
    ('CTG', ('ctg',), SPECIAL),
]

# Вид машины для спецтехники: (вид, ключевые слова — начало слова). Порядок важен: составные раньше простых.
MACHINE_KINDS: List[Tuple[str, Tuple[str, ...]]] = [
    ('Экскаватор-погрузчик', ('экскаватор-погрузчик', 'экскаватор погрузчик')),
    ('Экскаватор', ('экскаватор', 'excavator')),
    ('Автокран и кран', ('автокран', 'кран', 'crane', 'манипулятор', 'кму')),
    ('Погрузчик', ('погрузчик', 'телескопический', 'loader', 'вилочный')),
    ('Каток', ('каток', 'roller')),
    ('Бульдозер', ('бульдозер', 'bulldozer')),
    ('Автогрейдер', ('автогрейдер', 'грейдер', 'grader')),
    ('Асфальтоукладчик и фреза', ('асфальтоукладчик', 'фреза', 'ресайклер', 'укладчик')),
    ('Трактор и сельхозтехника', ('трактор', 'комбайн', 'сельхоз', 'опрыскиватель', 'сеялк')),
    ('Буровая техника', ('буров', 'сваебой', 'копер')),
    ('Дробильно-сортировочная', ('дробил', 'сортировоч', 'грохот')),
    ('Бетонная техника', ('бетоносмеситель', 'автобетон', 'бетононасос', 'растворобетон')),
    ('Вездеход и мототехника', ('вездеход', 'снегоболотоход', 'квадроцикл', 'снегоход')),
]
MACHINE_KIND_OTHER = 'Прочая спецтехника'

_TRAILER_WORDS = ('полуприцеп', 'прицеп', 'trailer')
_BUS_WORDS = ('автобус',)
# «Сильные» слова делают объект грузовым при любой марке (РЕНО-самосвал, мусоровоз на шасси JAC),
# «слабые» — только если марка не легковая и не LCV (Газель бортовая, фургон Sollers остаются LCV).
_TRUCK_STRONG_WORDS = ('тягач', 'самосвал', 'седельн', 'грузовой', 'мусоровоз', 'цистерн', 'топливозаправщик',
                       'эвакуатор', 'лесовоз', 'сортиментовоз', 'автотопливозаправщик')
_TRUCK_WEAK_WORDS = ('бортовой', 'изотерм', 'рефрижератор', 'шасси')
_LCV_WORDS = ('фургон', 'микроавтобус', 'пикап')
_EQUIPMENT_WORDS = ('оборудован', 'установка', 'станок', 'линия', 'комплект', 'генератор', 'компрессор', 'весы')


@dataclass(frozen=True)
class ObjectInfo:
    brand: str
    object_class: str
    machine_kind: str

    @property
    def class_label(self) -> str:
        return OBJECT_CLASS_LABELS.get(self.object_class, '')


def _word_pattern(variant: str) -> re.Pattern:
    return re.compile(r'(?<![0-9a-zа-яё])' + re.escape(variant) + r'(?![a-zа-яё])', re.IGNORECASE)


_BRAND_PATTERNS = sorted(
    ((_word_pattern(variant), brand, default_class) for brand, variants, default_class in BRANDS for variant in variants),
    key=lambda item: -len(item[0].pattern),  # длинные варианты раньше: «new holland» раньше «holland»
)


def _normalize(text: str) -> str:
    # латинские буквы, набранные вместо кириллических внутри русских слов («Паpоконвeктомат»), не мешают:
    # ключевые слова ищем по началу слова в нижнем регистре.
    return ' '.join((text or '').replace('ё', 'е').replace('Ё', 'Е').split()).lower()


def find_brand(text: str) -> Tuple[str, Optional[str]]:
    """(марка, класс по умолчанию) по самому раннему упоминанию марки в тексте."""
    best = None
    for pattern, brand, default_class in _BRAND_PATTERNS:
        match = pattern.search(text)
        if match and (best is None or match.start() < best[0]):
            best = (match.start(), brand, default_class)
    return (best[1], best[2]) if best else ('', None)


def _has_word(text: str, words) -> bool:
    return any(re.search(r'(?<![а-яa-z])' + re.escape(word), text) for word in words)


def machine_kind(text: str) -> str:
    for kind, words in MACHINE_KINDS:
        if _has_word(text, words):
            return kind
    return ''


def _first_position(text: str, words) -> Optional[int]:
    positions = [match.start() for word in words
                 for match in [re.search(r'(?<![а-яa-z])' + re.escape(word), text)] if match]
    return min(positions) if positions else None


def _dfa_kind(dfa_number: str) -> str:
    match = re.search(r'-(ЛА|ГА|ЛТ|ЛО)(?![А-ЯЁа-яё])', dfa_number or '')
    return match.group(1) if match else ''


def classify(text: str, insurance_type: str = '', dfa_number: str = '') -> ObjectInfo:
    normalized = _normalize(text)
    brand, brand_class = find_brand(normalized)
    kind = machine_kind(normalized)
    dfa = _dfa_kind(dfa_number)

    trailer_at = _first_position(normalized, _TRAILER_WORDS)
    tractor_at = _first_position(normalized, ('тягач',))
    if insurance_type == 'страхование имущества' and _has_word(normalized, _EQUIPMENT_WORDS):
        object_class = EQUIPMENT  # «Автомобильные весы ТОНАР», «Комплект автомоечного оборудования»
    elif trailer_at is not None and (tractor_at is None or trailer_at < tractor_at):
        object_class = TRAILER  # «тягач … и полуприцеп», «тягач для буксировки полуприцепов» — это тягач
    elif _has_word(normalized, _BUS_WORDS) and not _has_word(normalized, ('микроавтобус',)):
        object_class = BUS
    elif insurance_type == 'страхование спецтехники' or dfa == 'ЛТ' or (kind and brand_class != TRUCK):
        object_class = SPECIAL
    elif kind in ('Автокран и кран', 'Бетонная техника') and brand_class == TRUCK:
        object_class = SPECIAL  # автокран или автобетоносмеситель на грузовом шасси
    elif _has_word(normalized, _TRUCK_STRONG_WORDS) or (
            _has_word(normalized, _TRUCK_WEAK_WORDS) and brand_class not in (LCV, PASSENGER)):
        object_class = TRUCK
    elif brand_class in (PASSENGER, LCV, TRUCK, BUS, TRAILER):
        object_class = brand_class
        if brand_class == PASSENGER and _has_word(normalized, _LCV_WORDS):
            object_class = LCV
    elif brand_class == SPECIAL:
        object_class = SPECIAL
    elif _has_word(normalized, _TRUCK_WEAK_WORDS) or dfa == 'ГА':
        object_class = TRUCK
    elif _has_word(normalized, _LCV_WORDS):
        object_class = LCV
    elif dfa == 'ЛА':
        object_class = PASSENGER
    elif insurance_type == 'страхование имущества' or dfa == 'ЛО' or _has_word(normalized, _EQUIPMENT_WORDS):
        object_class = EQUIPMENT
    else:
        object_class = OTHER

    if object_class == SPECIAL and not kind:
        kind = MACHINE_KIND_OTHER
    if object_class != SPECIAL:
        kind = ''
    return ObjectInfo(brand=brand, object_class=object_class, machine_kind=kind)


def request_object_text(insurance_request) -> str:
    """Текст объекта заявки для классификации: описание, марка и модель (V2) или vehicle_info (V1)."""
    parts = [
        getattr(insurance_request, 'object_description', '') or '',
        getattr(insurance_request, 'vehicle_info', '') or '',
        getattr(insurance_request, 'brand', '') or '',
        getattr(insurance_request, 'model', '') or '',
    ]
    return ' '.join(part for part in parts if part)


def classify_request(insurance_request) -> ObjectInfo:
    return classify(
        request_object_text(insurance_request),
        getattr(insurance_request, 'insurance_type', '') or '',
        getattr(insurance_request, 'dfa_number', '') or '',
    )
