# Solo VPS

[English](README.md) · [Русский](README.ru.md)

**Превратите чистый Ubuntu VPS в готовый сервер для своих приложений.** Пройдите инструкцию и выполните несколько основных команд. Solo VPS настроит Linux, SSH, firewall, Docker и Coolify, а затем проверит, что всё работает.

Вам не придётся сначала проектировать инфраструктуру и выбирать между десятками инструментов. Solo VPS уже выбрал практичный стек, подготовил настройки и автоматизацию и объяснил, как деплоить, проверять и восстанавливать приложения. После настройки можно вернуться к коду, а не продолжать собирать сервер вручную.

> **Статус:** PRE-ALPHA — **не готово к production**. Используйте тестовый VPS. Базовый путь VPS → Coolify → первое приложение → автоматический деплой уже подтверждён на реальном тестовом сервере. Точная release-кандидат версия всё ещё требует полного прогона с чистого VPS и отдельных recovery/maintenance проверок. Внешние бэкапы и Grafana остаются дополнительными профилями.

```text
ваш компьютер
        │
        │  setup → apply → secure → platform → verify
        ▼
Ubuntu 24.04 LTS VPS
        ├── защищённый host + Docker
        └── Coolify
              └── ваши приложения

GitHub Actions → GHCR → Coolify
SOPS + age → infrastructure/recovery secrets
Optional: restic → managed off-site object storage
```

## Что такое Solo VPS

Solo VPS — это готовый способ настроить сервер для solo-разработчика или небольшого проекта. Это одновременно автоматизация и пошаговая инструкция: в начале у вас чистый **Ubuntu 24.04 LTS** VPS, а в конце — защищённый сервер, панель управления деплоями и понятный путь для CI/CD, логов, резервных копий и восстановления.

Проект специально принимает основные решения за вас. Вместо набора несвязанных вариантов он сразу отвечает на важные вопросы: какую ОС использовать, как защитить доступ, как запускать контейнеры, где деплоить приложения, где хранить образы и как делать резервные копии.

После базовой настройки вы сможете:

- отправлять код в GitHub и автоматически выкатывать новую версию;
- управлять приложениями, доменами, HTTPS, переменными, базами данных и живыми логами через Coolify;
- проверять состояние сервера одной командой проекта;
- по следующим главам добавить историю логов, внешний мониторинг и резервные копии вне VPS.

## Стек, который уже выбран за вас

| Технология | Для чего она нужна | Почему она выбрана |
| --- | --- | --- |
| **Ubuntu 24.04 LTS** | Базовая операционная система | Стабильная, распространённая и предсказуемая основа для одного VPS |
| **Ansible** | Настраивает пользователей, SSH, firewall, обновления и Docker | Позволяет повторить настройку и не редактировать сервер вручную десятками команд |
| **Docker** | Запускает приложения и сервисы в контейнерах | Даёт приложениям одинаковый формат и окружение запуска |
| **Coolify** | Деплои, домены, HTTPS, переменные, базы данных и живые логи | Даёт удобную панель для ежедневной работы без создания собственной платформы |
| **GitHub Actions + GHCR** | Проверяют код, собирают образы и передают их в Coolify | Связывают сборку и деплой с обычным `git push` |
| **SOPS + age** | Шифруют инфраструктурные секреты и данные для восстановления | Позволяют безопасно хранить зашифрованные файлы вне VPS |
| **restic + S3-совместимое хранилище** *(дополнительно)* | Хранят резервные копии отдельно от сервера | Потеря VPS не должна уничтожить его резервные копии |
| **Grafana Cloud и внешний uptime-мониторинг** *(дополнительно)* | История логов, метрики сервера и уведомления о сбоях | Помогают разобраться в проблеме, даже если VPS или старый контейнер уже недоступны |

Solo VPS рассчитан на один сервер. Это **не** Kubernetes, не multi-node orchestrator и не вторая реализация Coolify. Core profile имеет **нулевую зависимость от Tailscale, Grafana/Alloy, error tracking, pgAdmin или shell customization**.

## Текущий статус

Host, SSH, Docker, Coolify, CI и ограниченный image rollback реализованы в исходниках. На тестовом VPS уже подтверждены fresh Ubuntu 24.04 setup, host apply, передача окружения администратору, SSH hardening, установка Coolify, первое приложение, автоматический деплой после merge, изменение runtime ENV и live-логи приложения. Это ещё не финальный clean replay точной release-кандидат версии. Отдельно остаются проверка продолжения после прерывания, реальное обновление Coolify, трёхдневная проверка retention логов и полное восстановление потерянного VPS. Restore PostgreSQL, off-site backup/restore и Grafana host metrics/alerting уже подтверждены на реальном VPS, как и доставка логов в Grafana до/после redeploy и после перезапуска Alloy.

До появления этих proofs считайте локальную/static validation development evidence, а не production-гарантией.

Этот README — **канонический текущий пользовательский контракт**. [`ROADMAP.md`](ROADMAP.md) отражает состояние разработки и следующую работу. [`PROJECT_PASSPORT.md`](PROJECT_PASSPORT.md) — north-star architecture contract, **а не текущий implementation status**.

## Что изменяет `make bootstrap`

`make bootstrap` — низкоуровневая операция host baseline, которую использует нормальный `make apply` flow. После preflight она может:

- настроить hostname и timezone;
- создать managed non-root администратора и проверенную passwordless sudo policy;
- настроить UFW host-input baseline;
- включить unattended Ubuntu security updates без автоматической перезагрузки;
- установить и настроить Docker Engine, Buildx и Compose.

Она намеренно **не устанавливает Coolify**, **не активирует SSH hardening**, не создаёт production secrets, не настраивает off-site storage и не деплоит приложения.

Для обычного onboarding используйте `make apply`, а не собирайте путь вручную из low-level component targets.

## Быстрый старт

Поддерживаемый alpha-путь — **один чистый VPS с Ubuntu 24.04 LTS**, минимум **2 vCPU, 2 GiB RAM и 30 GiB свободного места**. Нужны SSH-доступ под root, консоль восстановления провайдера, входящие TCP 22/80/443, домен с доступом к DNS и компьютер с Windows PowerShell или Linux, SSH и SCP. Make/Ansible из инструкции запускаются на VPS; для локальных Linux-инструментов на Windows подходит WSL.

Пройдите две части инструкции по порядку. В них собраны все обязательные команды и действия в интерфейсе, с примерами для Windows PowerShell и Linux. [Репозиторий исходников](https://github.com/paracosm17/solo-vps) уже открыт, но проверенного релиза и тега `v0.1.0` пока нет. Для тестирования выберите и запишите полный commit ID проверенной версии; не считайте текущую ветку `main` готовым релизом.

1. **[Настройте VPS и Coolify](docs/quick-start.ru.md)** — от `apt-get update` до доступа администратора, защищённого SSH, регистрации в Coolify и панели через HTTPS.
2. **[Запустите приложение и настройте CI/CD](docs/operations/first-app.ru.md)** — репозиторий GitHub, образ GHCR, первый деплой, отдельный CI-ключ и пользователь, настройки GitHub/Coolify, автоматический деплой, runtime ENV/секреты и живые логи.

Команды настройки сервера: `make setup → make apply → make secure → make platform → make verify`. Выполняйте их в местах, указанных в первой части, включая проверку входа под администратором перед защитой SSH.

Базовая настройка заканчивается после второй части. Внешние резервные копии, уведомления о сбоях и сохранение истории логов — следующие задачи; ссылки находятся в её конце.

**Ограничения alpha:** точная версия релиза ещё требует повтора на чистом VPS, проверки жизненного цикла и прерванного обновления Coolify, оповещения о падении всего VPS, отложенной проверки истории логов и восстановления потерянного VPS. Используйте временный тестовый сервер; локальные проверки и прежние операторские прогоны не подтверждают готовность к production.

## Safety boundaries

- Пока проект PRE-ALPHA, используйте disposable/test VPS.
- Перед изменением SSH, sudo или firewall сохраняйте доступ к provider console/rescue.
- Никогда не коммитьте private SSH keys, age identities, S3 credentials, restic passwords, API tokens или application secrets.
- UFW — host-input baseline; Docker-published ports проверяются отдельно.
- Membership в Docker group фактически root-equivalent и ограничен уже привилегированным managed administrator.
- Source checks не доказывают clean-host installation, hosted CI, настоящий off-site backup, настоящий restore или disaster recovery.

## Документация

**Начните здесь:**

- **[Быстрый старт](docs/quick-start.ru.md)** — от свежего VPS до проверенного Coolify.
- **[Первое приложение](docs/operations/first-app.ru.md)** — guided tutorial с hello-app.
- **[Ежедневная работа](docs/operations/operator-ui.ru.md)** — где деплоить, смотреть логи, менять runtime config и проверять CI.
- **[После базовой настройки](docs/operations/after-basic-setup.ru.md)** — рекомендуемый порядок: история логов, backup БД, уведомления о сбоях и восстановление.
- **[История логов приложений](docs/operations/observability.ru.md)** — сохраняйте логи и ищите их даже после нового деплоя.
- **[Backup и restore PostgreSQL](docs/operations/postgresql-backups.ru.md)** — создайте локальную копию в Coolify и докажите её восстановлением в отдельную БД.
- **[Внешний uptime](docs/operations/external-uptime.ru.md)** — глава 5: получите независимые уведомления о падении и восстановлении.
- **[Резервные копии вне VPS](docs/operations/offsite-backups.ru.md)** — глава 6: вынесите копии PostgreSQL, Coolify и нужных файлов во внешнее хранилище и докажите восстановление.
- **[Метрики VPS](docs/operations/metrics.ru.md)** — глава 7: отправьте небольшой набор CPU/memory/disk metrics в Grafana Cloud и проверьте один полезный alert.
- **[Сбои и обслуживание](docs/operations/incidents-and-maintenance.ru.md)** — разберите сбой CI или production и используйте checklist планового обслуживания.
- **[Справочник backup/recovery](docs/backups-restic.ru.md)** — детали restic и границы восстановления.
- **[Обновления](docs/upgrades.ru.md)** — поддерживаемый lifecycle Docker/Coolify.
- **[Восстановление потерянного VPS](docs/disaster-recovery.ru.md)** — процедура для replacement server.
- **[Справочник команд](docs/command-reference.ru.md)** — публичные и advanced Make targets.

Полная task-oriented карта находится в **[`docs/index.ru.md`](docs/index.ru.md)**.

Запустить эту же документацию как Material for MkDocs site:

```bash
make docs
```

Строгая сборка, которую использует documentation CI:

```bash
make docs-build
```

Сайт документации по умолчанию открывается на английском; переключатель языка в header позволяет перейти на русский вариант той же страницы.

Политика и дизайн проекта: [`SECURITY.md`](SECURITY.md), [`CONTRIBUTING.md`](CONTRIBUTING.md), [`docs/architecture.ru.md`](docs/architecture.ru.md), [`LICENSE`](LICENSE) и [`Apache-2.0 decision`](docs/license-choice.ru.md).

Повторный `make apply` использует настроенный admin inventory. `make platform` проверяет готовую установку либо продолжает свою прерванную установку; не удаляйте `/data/coolify`. `make verify` проверяет активированные SSH/Coolify и отвергает незавершённые транзакции.
