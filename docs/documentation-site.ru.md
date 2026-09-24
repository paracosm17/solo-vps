# Сайт документации

Документация Solo VPS хранится в обычном Markdown и рендерится через **Material for MkDocs**. Английский — язык сайта по умолчанию; у каждой публикуемой страницы есть русская версия, доступная через переключатель языка в header.

Markdown-файлы в `docs/` остаются source of truth. Theme overrides находятся в `overrides/`, а визуальный слой — в `docs/stylesheets/extra.css` и `docs/assets/brand/`.

## Локальный preview

На Windows дважды щёлкните `docs.bat` в корне репозитория или запустите его из PowerShell:

```powershell
.\docs.bat
```

Батник создаёт `.venv-docs`, устанавливает закреплённые зависимости документации и запускает сайт по адресу `http://127.0.0.1:8000/`. Русская версия: `http://127.0.0.1:8000/ru/`. Дождитесь сообщения о запуске сервера и откройте адрес в браузере. Оставьте окно терминала открытым; для остановки нажмите `Ctrl+C`. Изменения Markdown появляются после автоматической пересборки.

Для первого запуска нужны Python 3.12 или новее и интернет. Make, WSL и активация окружения в PowerShell не требуются. Если Python отсутствует в PATH и не зарегистрирован в `py`, задайте переменную `DOCS_PYTHON` с полным путём к `python.exe`. Команда `.\docs.bat build` выполняет строгую статическую сборку. Если порт 8000 занят, остановите предыдущий preview перед новым запуском.

На Linux/macOS из корня репозитория:

```bash
make docs
```

Первый запуск создаёт изолированное окружение `.venv-docs` и устанавливает `requirements-docs.txt`. Откройте локальный адрес, который выведет MkDocs — обычно `http://127.0.0.1:8000/`.

Стек документации намеренно закреплён на `MkDocs 1.6.1`: текущий сайт использует plugin API и Material theme overrides поколения MkDocs 1.x. Не обновляйте MkDocs до 2.x без отдельной миграции docs stack.

Нажмите `Ctrl+C`, чтобы остановить preview server.

## Сборка как в CI

```bash
make docs-build
```

Команда выполняет:

```bash
mkdocs build --strict
```

Сгенерированный статический сайт записывается в `site/`. Любой warning strict-build рассматривайте как documentation debt, а не подавляйте его по умолчанию.

Material 9.7.2+ перед прямым запуском `mkdocs` печатает upstream-уведомление о несовместимости с будущим MkDocs 2.0. Это информационный banner, а не MkDocs build warning. `make docs`, `make docs-build` и docs CI задают `NO_MKDOCS_2_WARNING=1`; для прямой команды в PowerShell можно скрыть его в текущем окне:

```powershell
$env:NO_MKDOCS_2_WARNING="1"
mkdocs build --strict
```

## Запуск без Make

Linux/macOS:

```bash
python3 -m venv .venv-docs
source .venv-docs/bin/activate
python -m pip install -r requirements-docs.txt
mkdocs serve
```

Windows PowerShell:

```powershell
py -m venv .venv-docs
.\.venv-docs\Scripts\Activate.ps1
python -m pip install -r requirements-docs.txt
mkdocs serve
```

Если PowerShell блокирует активацию virtual environment, разрешите выполнение scripts только в текущем окне:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

## Контракт локализации

`mkdocs-static-i18n` использует suffix structure:

```text
docs/quick-start.md       -> /
docs/quick-start.ru.md    -> /ru/
```

Markdown-ссылки остаются language-neutral: например, обе локализованные source-страницы ссылаются на `quick-start.md`, а не на `quick-start.ru.md`. Во время build plugin сам выбирает правильный localized target. MkDocs не переписывает `href` внутри raw HTML, поэтому там используйте built pretty URL, например `href="quick-start/"`, и никогда `href="quick-start.md"`.

При изменении публикуемой английской страницы обновляйте её `.ru.md`-пару в том же change set. Не переводите команды, file paths, configuration keys, environment variables, API fields, Make targets и machine-readable confirmation tokens.

Внутренние release/evidence pages остаются в репозитории и намеренно исключены из публичного пользовательского сайта.

## Визуальная кастомизация

Material используется как engine, а не как готовая визуальная идентичность. Цвета, типографика, состояния навигации, карточки и code blocks определены в `docs/stylesheets/extra.css`. Видимая кнопка выбора языка реализована небольшим override Material alternate-language partial в `overrides/partials/alternate.html`. `overrides/main.html` не даёт Material 9.7 выполнять ошибочные per-page sitemap requests; localized sitemap по-прежнему формирует `mkdocs-static-i18n`.

Держите overrides узкими. Предпочитайте CSS и документированные extension points Material копированию больших upstream templates.

## GitHub Pages

`.github/workflows/docs.yml` проверяет сайт строгой сборкой в pull requests с изменениями документации. Изменения в `docs/` и `overrides/` запускают workflow. Push в `main` загружает собранный сайт как Pages artifact и публикует его через окружение `github-pages`.

Для публичного репозитория `https://github.com/paracosm17/solo-vps`:

1. Откройте **Settings → Pages** репозитория.
2. В **Build and deployment → Source** выберите **GitHub Actions**. Ограничьте окружение `github-pages` веткой по умолчанию.
3. Укажите фактический Pages URL в `site_url` файла `mkdocs.yml`, включая путь репозитория и завершающий `/` для project site. Это сохраняет корректные языковые ссылки.
4. Убедитесь, что `main` — ветка по умолчанию; `repo_url` и `edit_uri: edit/main/docs/` уже настроены.
5. Перед коммитом изменения URL выполните `make docs-build`, затем проверьте публикацию, ссылки EN/RU и ссылки редактирования.

Не добавляйте предполагаемый Pages URL или production documentation domain до появления этих ресурсов.

## Политика навигации

`mkdocs.yml` организован вокруг пользовательских задач. Новые user-facing страницы должны попадать в самый узкий подходящий раздел, а не повторять структуру Ansible roles или внутреннее устройство репозитория.

Release evidence, clean-target procedures и глубокие maintainer tests остаются в репозитории, а не занимают публичную product navigation.
