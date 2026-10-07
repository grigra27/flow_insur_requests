"""Сборка шаблона ответа страховщика V1: templates/flow_answer_template.xlsx.

Сама раскладка — в summaries/response_template.py (там же шаблон V2). Шаблон V1 отдаётся
сотрудникам кнопкой «Скачать актуальный шаблон ответа»; после правок раскладки пересоберите файл
и закоммитьте его (тест summaries.test_response_template_v2 сверяет файл со сборщиком).

Запуск из корня проекта:
    python scripts/build_flow_answer_template.py [путь_к_xlsx]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from summaries.response_template import V1_TEMPLATE_PATH, build_v1  # noqa: E402


def build(output: Path = V1_TEMPLATE_PATH) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(build_v1())
    return output


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else V1_TEMPLATE_PATH
    print(build(target))
