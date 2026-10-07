<p align="center">
  <img src="docs/assets/brand/solo-vps-mark.svg" width="72" height="72" alt="">
</p>
<h1 align="center">Solo VPS</h1>
<p align="center"><strong>Ваши приложения. Один VPS. Деплой из Git.</strong></p>
<p align="center">
  <a href="https://github.com/paracosm17/solo-vps/actions/workflows/repository-ci.yml"><img src="https://github.com/paracosm17/solo-vps/actions/workflows/repository-ci.yml/badge.svg?branch=main" alt="Repository CI"></a>
  <a href="https://paracosm17.github.io/solo-vps/ru/"><img src="https://img.shields.io/badge/docs-English%20%2F%20Русский-3273dc" alt="Документация на русском и английском"></a>
  <a href="https://paracosm17.github.io/solo-vps/ru/quick-start/"><img src="https://img.shields.io/badge/Ubuntu-24.04%20LTS-E95420?logo=ubuntu&amp;logoColor=white" alt="Ubuntu 24.04 LTS"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-2ea44f" alt="Лицензия Apache-2.0"></a>
</p>
<p align="center">
  <a href="https://paracosm17.github.io/solo-vps/ru/quick-start/"><strong>Начать установку</strong></a> ·
  <a href="https://paracosm17.github.io/solo-vps/ru/">Документация</a> ·
  <a href="https://github.com/paracosm17/solo-vps/issues">Сообщить об ошибке</a> ·
  <a href="README.md">English</a>
</p>

Solo VPS настраивает сервер Ubuntu для ваших приложений: создаёт администратора, настраивает SSH, сетевой экран и Docker, устанавливает **Coolify**. Пошаговая инструкция помогает подключить автоматический деплой через **GitHub Actions и GHCR**.

Проект рассчитан на разработчиков, которые размещают собственные сервисы, пет-проекты или небольшие продукты на VPS. Настройка сервера воспроизводится командами; повседневная работа с деплоями, переменными и логами доступна через GitHub и панель Coolify.

## Возможности

- **Повторяемая настройка сервера.** Ansible создаёт администратора, настраивает SSH-ключи, сетевой экран, обновления безопасности и Docker.
- **Деплой после push.** Готовый workflow проверяет код, собирает образ в GitHub Actions, публикует его в GHCR и разворачивает через Coolify. Сборка не нагружает VPS.
- **Панель для ежедневной работы.** Домены, HTTPS, настройки приложений, базы данных, деплои и текущие логи — в Coolify.
- **Проверка и обслуживание.** Команды проекта проверяют конфигурацию сервера; инструкции описывают обновление, неудачный деплой и восстановление.
- **Резервные копии по мере необходимости.** Подключите копии PostgreSQL, зашифрованные внешние бэкапы через restic и проверьте восстановление по инструкции.
- **Мониторинг по мере необходимости.** Добавьте внешние уведомления о сбоях, историю логов и метрики VPS через управляемые сервисы.

## Как это работает

![Git push → GitHub Actions проверяет код и собирает образ → GHCR хранит образ → Coolify разворачивает его на VPS](docs/assets/brand/delivery-flow.svg)

**Solo VPS настраивает сервер. Coolify запускает приложения. GitHub Actions собирает образы.** После подключения CI/CD отправка кода в `main` приложения запускает проверки и деплой. Результат виден в GitHub и Coolify — заходить по SSH для каждого выпуска не требуется.

Поддерживаемая схема — **один VPS для приложений**. Проверенная версия Coolify, исходная версия для обновления и уровень проверки заданы в [манифесте версии](config/coolify-release.yml); порядок перехода описан в [обновлениях](docs/upgrades.ru.md). Резервные копии и мониторинг подключаются отдельно, после запуска первого приложения. Кластеры, высокая доступность и автоматическое управление доступом команды в текущую версию не входят.

## Быстрый старт

### Что потребуется

| Что | Требования |
| --- | --- |
| Сервер | Чистый VPS с **Ubuntu 24.04 LTS**; минимум **2 vCPU, 2 GiB RAM и 30 GiB свободного места** |
| Доступ | Первоначальный SSH-вход под root, консоль восстановления провайдера и входящие TCP-порты **22, 80 и 443** |
| Домен | Домен и возможность редактировать DNS-записи |
| Компьютер | **Windows PowerShell или Linux/WSL**, с SSH и SCP |
| CI/CD | Аккаунт GitHub для предложенного workflow GitHub Actions / GHCR |

Это минимальные ресурсы для установки. Для приложений и баз данных потребуется дополнительный запас.

### Установка и первый деплой

Пройдите две инструкции по порядку. В них собраны команды, настройки и действия в браузере для Windows и Linux/WSL:

1. **[Настройте VPS и Coolify](https://paracosm17.github.io/solo-vps/ru/quick-start/)** — настройте Ubuntu и доступ администратора, установите Docker и Coolify, откройте панель через HTTPS.
2. **[Запустите приложение и подключите CI/CD](https://paracosm17.github.io/solo-vps/ru/operations/first-app/)** — опубликуйте образ, разверните учебное приложение, включите автоматические обновления и попробуйте переменные и логи.

Настройка сервера проходит в таком порядке:

```text
make setup → make apply → make secure → make platform → make verify
```

Выполняйте каждую команду в указанном месте первой инструкции: перед защитой SSH нужно заполнить конфигурацию и проверить вход под администратором. Make и Ansible во время установки работают на VPS; команды для компьютера приведены отдельно для PowerShell и Linux/WSL.

После второй части базовая настройка закончена. Можно переходить к своему приложению и подключать нужные ему дополнительные возможности.

## Документация

| Задача | Инструкция |
| --- | --- |
| Управлять деплоями, переменными и текущими логами | [Ежедневная работа](https://paracosm17.github.io/solo-vps/ru/operations/operator-ui/) |
| Выбрать следующие шаги настройки | [После базовой настройки](https://paracosm17.github.io/solo-vps/ru/operations/after-basic-setup/) |
| Сделать копию базы или сервера | [PostgreSQL](https://paracosm17.github.io/solo-vps/ru/operations/postgresql-backups/) · [Внешние копии](https://paracosm17.github.io/solo-vps/ru/operations/offsite-backups/) |
| Добавить уведомления, историю логов или метрики | [Uptime](https://paracosm17.github.io/solo-vps/ru/operations/external-uptime/) · [Логи](https://paracosm17.github.io/solo-vps/ru/operations/observability/) · [Метрики](https://paracosm17.github.io/solo-vps/ru/operations/metrics/) |
| Обновить или восстановить установку | [Обновления](https://paracosm17.github.io/solo-vps/ru/upgrades/) · [Восстановление VPS](https://paracosm17.github.io/solo-vps/ru/disaster-recovery/) |
| Найти нужную команду | [Справочник команд](https://paracosm17.github.io/solo-vps/ru/command-reference/) |

Перед размещением важных данных сохраните резервные копии и данные доступа для восстановления вне VPS. Откат деплоя возвращает образ приложения, но не отменяет миграции базы и изменения данных.

## Участие и поддержка

Сообщения об ошибках, исправления документации и небольшие улучшения приветствуются. Начните с [`CONTRIBUTING.md`](CONTRIBUTING.md). Об уязвимостях сообщайте приватно по инструкции в [`SECURITY.md`](SECURITY.md).

<details>
<summary>Устройство проекта и разработка</summary>

- [Архитектура](docs/architecture.ru.md) и [границы проекта](PROJECT_PASSPORT.md).
- [План развития и результаты проверок](ROADMAP.md).
- [История изменений](CHANGELOG.md) и [порядок выпуска](docs/release-process.md).
- [Правила работы с документацией](.github/DOCUMENTATION.md).

</details>

## Лицензия

[Apache License 2.0](LICENSE). Условия внесения изменений описаны в [решении о лицензии](docs/license-choice.ru.md).
