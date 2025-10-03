# Руководство по конвертации USER_MANUAL.md в PDF

Это краткое руководство по созданию PDF версии руководства пользователя.

---

## Предварительные требования

### Установка Pandoc

**macOS:**
```bash
brew install pandoc
brew install basictex  # Для PDF конвертации
```

**Альтернативный способ:**
Скачайте установщик с официального сайта: https://pandoc.org/installing.html

### Проверка установки

```bash
pandoc --version
```

Должна отобразиться версия Pandoc (например, 3.1.x или выше).

---

## Базовая конвертация

### Простая конвертация в PDF

```bash
pandoc docs/USER_MANUAL.md -o docs/USER_MANUAL.pdf
```

### Конвертация с оглавлением

```bash
pandoc docs/USER_MANUAL.md \
  -o docs/USER_MANUAL.pdf \
  --toc \
  --toc-depth=3 \
  --number-sections
```

---

## Рекомендуемая конвертация

### Полная конвертация с настройками

```bash
pandoc docs/USER_MANUAL.md \
  -o docs/USER_MANUAL.pdf \
  --toc \
  --toc-depth=3 \
  --number-sections \
  --pdf-engine=xelatex \
  -V lang=ru \
  -V papersize=a4 \
  -V geometry:margin=2cm \
  -V fontsize=11pt \
  -V mainfont="DejaVu Sans" \
  -V monofont="DejaVu Sans Mono"
```

### Объяснение параметров:

- `--toc` - добавить оглавление
- `--toc-depth=3` - глубина оглавления (до 3 уровня)
- `--number-sections` - нумеровать разделы
- `--pdf-engine=xelatex` - использовать XeLaTeX (лучше для русского языка)
- `-V lang=ru` - язык документа - русский
- `-V papersize=a4` - формат бумаги A4
- `-V geometry:margin=2cm` - поля 2 см со всех сторон
- `-V fontsize=11pt` - размер шрифта 11 пунктов
- `-V mainfont="DejaVu Sans"` - основной шрифт (поддерживает кириллицу)
- `-V monofont="DejaVu Sans Mono"` - моноширинный шрифт для кода

---

## Конвертация в HTML

### Базовая HTML версия

```bash
pandoc docs/USER_MANUAL.md \
  -o docs/USER_MANUAL.html \
  --standalone
```

### HTML с оглавлением и стилями

```bash
pandoc docs/USER_MANUAL.md \
  -o docs/USER_MANUAL.html \
  --toc \
  --toc-depth=3 \
  --number-sections \
  --standalone \
  --css=style.css \
  --self-contained
```

---

## Добавление скриншотов

### Подготовка скриншотов

1. Создайте папку для изображений:
```bash
mkdir -p docs/images
```

2. Сделайте скриншоты всех 33 указанных мест в документе

3. Сохраните их с понятными именами:
   - `screenshot-01-login-page.png`
   - `screenshot-02-main-page.png`
   - и т.д.

### Замена плейсхолдеров на изображения

Найдите в документе строки вида:
```markdown
[Место для скриншота: страница входа в систему с формой авторизации]
```

Замените на:
```markdown
![Страница входа в систему с формой авторизации](images/screenshot-01-login-page.png)
```

### Автоматическая замена (опционально)

Можно использовать скрипт для автоматической замены:

```bash
# Создайте файл replace-screenshots.sh
cat > replace-screenshots.sh << 'EOF'
#!/bin/bash

# Копируем оригинал
cp docs/USER_MANUAL.md docs/USER_MANUAL_with_images.md

# Заменяем плейсхолдеры (пример для первого скриншота)
sed -i '' 's/\[Место для скриншота: страница входа в систему с формой авторизации\]/![Страница входа](images\/screenshot-01-login-page.png)/g' docs/USER_MANUAL_with_images.md

# Добавьте аналогичные строки для остальных 32 скриншотов
# ...

echo "Замена завершена! Файл: docs/USER_MANUAL_with_images.md"
EOF

chmod +x replace-screenshots.sh
./replace-screenshots.sh
```

---

## Создание версии для печати

### PDF с разрывами страниц

Для лучшего форматирования при печати добавьте разрывы страниц перед основными разделами:

```bash
pandoc docs/USER_MANUAL.md \
  -o docs/USER_MANUAL_print.pdf \
  --toc \
  --toc-depth=3 \
  --number-sections \
  --pdf-engine=xelatex \
  -V lang=ru \
  -V papersize=a4 \
  -V geometry:margin=2.5cm \
  -V fontsize=11pt \
  -V documentclass=report \
  -V classoption=twoside
```

Параметры для печати:
- `margin=2.5cm` - увеличенные поля для переплета
- `documentclass=report` - класс документа для книг
- `classoption=twoside` - двусторонняя печать

---

## Решение проблем

### Ошибка: "xelatex not found"

**Решение:**
```bash
# macOS
brew install basictex
sudo tlmgr update --self
sudo tlmgr install collection-xetex

# Или установите полный MacTeX
brew install --cask mactex
```

### Ошибка: "Font not found"

**Решение:**
Используйте системные шрифты или установите DejaVu:
```bash
brew tap homebrew/cask-fonts
brew install font-dejavu
```

Или укажите другой шрифт:
```bash
-V mainfont="Arial" \
-V monofont="Courier New"
```

### Проблемы с кириллицей

**Решение:**
Обязательно используйте:
- `--pdf-engine=xelatex` (не pdflatex!)
- `-V lang=ru`
- Шрифт с поддержкой кириллицы

### PDF слишком большой

**Решение:**
Оптимизируйте изображения перед добавлением:
```bash
# Установите ImageMagick
brew install imagemagick

# Оптимизируйте все PNG
for img in docs/images/*.png; do
  convert "$img" -quality 85 -resize 1200x "$img"
done
```

---

## Автоматизация

### Создание скрипта для конвертации

Создайте файл `build-manual.sh`:

```bash
#!/bin/bash

echo "🔨 Создание PDF версии руководства пользователя..."

pandoc docs/USER_MANUAL.md \
  -o docs/USER_MANUAL.pdf \
  --toc \
  --toc-depth=3 \
  --number-sections \
  --pdf-engine=xelatex \
  -V lang=ru \
  -V papersize=a4 \
  -V geometry:margin=2cm \
  -V fontsize=11pt \
  -V mainfont="DejaVu Sans" \
  -V monofont="DejaVu Sans Mono"

if [ $? -eq 0 ]; then
  echo "✅ PDF создан успешно: docs/USER_MANUAL.pdf"
  
  # Показать размер файла
  ls -lh docs/USER_MANUAL.pdf | awk '{print "📦 Размер файла:", $5}'
  
  # Открыть PDF (опционально)
  # open docs/USER_MANUAL.pdf
else
  echo "❌ Ошибка при создании PDF"
  exit 1
fi

echo ""
echo "🌐 Создание HTML версии..."

pandoc docs/USER_MANUAL.md \
  -o docs/USER_MANUAL.html \
  --toc \
  --toc-depth=3 \
  --number-sections \
  --standalone \
  --self-contained

if [ $? -eq 0 ]; then
  echo "✅ HTML создан успешно: docs/USER_MANUAL.html"
  ls -lh docs/USER_MANUAL.html | awk '{print "📦 Размер файла:", $5}'
else
  echo "❌ Ошибка при создании HTML"
  exit 1
fi

echo ""
echo "🎉 Готово!"
```

Сделайте скрипт исполняемым и запустите:

```bash
chmod +x build-manual.sh
./build-manual.sh
```

---

## Проверка результата

### Откройте PDF

```bash
# macOS
open docs/USER_MANUAL.pdf

# Linux
xdg-open docs/USER_MANUAL.pdf

# Windows
start docs/USER_MANUAL.pdf
```

### Проверьте:

- ✅ Оглавление присутствует и кликабельно
- ✅ Разделы пронумерованы
- ✅ Русский текст отображается корректно
- ✅ Таблицы форматированы правильно
- ✅ Блоки кода читаемы
- ✅ Эмодзи отображаются (или заменены на текст)
- ✅ Ссылки работают (внутренние)

---

## Дополнительные ресурсы

- **Документация Pandoc:** https://pandoc.org/MANUAL.html
- **Шаблоны Pandoc:** https://github.com/Wandmalfarbe/pandoc-latex-template
- **Руководство по LaTeX:** https://www.latex-project.org/help/documentation/

---

## Контрольный список

Перед финальной публикацией PDF:

- [ ] Все скриншоты добавлены (33 шт.)
- [ ] Оглавление корректно
- [ ] Нумерация страниц правильная
- [ ] Все ссылки работают
- [ ] Таблицы не обрезаны
- [ ] Код читаем
- [ ] Русский текст без ошибок
- [ ] Размер файла приемлемый (< 50 МБ)
- [ ] PDF открывается на всех устройствах
- [ ] Версия и дата актуальны

---

**Удачи с созданием PDF! 📄✨**
