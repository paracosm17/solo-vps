# Solo VPS

<p class="solo-home-intro" data-solo-home><strong>Возьмите чистый Ubuntu VPS и получите готовый сервер для своих приложений.</strong> Solo VPS уже выбрал стек, подготовил настройки и автоматизацию и проведёт вас через несколько основных команд и обязательных действий в интерфейсах.</p>

Вам не нужно быть DevOps-инженером. Следуйте инструкции — Solo VPS настроит защищённый доступ, firewall, Docker и Coolify. После этого вы будете деплоить приложения через GitHub и управлять ими в Coolify, а не собирать инфраструктуру вручную.

<div class="solo-status">
  <svg class="solo-status__icon" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 2.75 22 20H2L12 2.75Zm0 5.1a1 1 0 0 0-1 1v5.25a1 1 0 1 0 2 0V8.85a1 1 0 0 0-1-1Zm0 9.05a1.15 1.15 0 1 0 0 2.3 1.15 1.15 0 0 0 0-2.3Z"/></svg>
  <div class="solo-status__body"><strong>PRE-ALPHA</strong>Пока используйте тестовый VPS. Полная установка и восстановление ещё проходят проверку.</div>
</div>

## С чего начать

Если вы устанавливаете Solo VPS впервые, пройдите части 1 и 2 по порядку. Это вся базовая настройка до CI/CD, переменных окружения и живых логов. Читать архитектуру и внутреннее устройство проекта перед установкой не требуется. Затем откройте [«После базовой настройки»](operations/after-basic-setup.md) и добавьте то, что нужно вашему приложению для нормальной эксплуатации.

<div class="solo-start-grid">
  <a class="solo-start-card" href="quick-start/">
    <span class="solo-start-card__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M5 12h14M13 6l6 6-6 6"/></svg></span>
    <span><span class="solo-start-card__title">1. VPS и Coolify</span><span class="solo-start-card__copy">От чистой Ubuntu до входа под администратором и панели Coolify через HTTPS.</span></span>
    <span class="solo-start-card__arrow">→</span>
  </a>
  <a class="solo-start-card" href="operations/first-app/">
    <span class="solo-start-card__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M12 3l8 4.5v9L12 21l-8-4.5v-9L12 3Zm0 9 8-4.5M12 12 4 7.5M12 12v9"/></svg></span>
    <span><span class="solo-start-card__title">2. Приложение и CI/CD</span><span class="solo-start-card__copy">Создайте демо, включите деплой из GitHub, задайте ENV и посмотрите логи — всё на одной странице.</span></span>
    <span class="solo-start-card__arrow">→</span>
  </a>
  <a class="solo-start-card" href="operations/operator-ui/">
    <span class="solo-start-card__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M4 5h16v14H4zM8 9h8M8 13h5"/></svg></span>
    <span><span class="solo-start-card__title">Ежедневная работа</span><span class="solo-start-card__copy">Где смотреть деплои, переменные, логи, health checks и диагностику.</span></span>
    <span class="solo-start-card__arrow">→</span>
  </a>
  <a class="solo-start-card" href="operations/offsite-backups/">
    <span class="solo-start-card__icon"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M4 12a8 8 0 1 0 2.3-5.7L4 8.6M4 4v4.6h4.6"/></svg></span>
    <span><span class="solo-start-card__title">Резервные копии</span><span class="solo-start-card__copy">Вынесите копии PostgreSQL, Coolify и нужных файлов с VPS и проверьте реальное восстановление.</span></span>
    <span class="solo-start-card__arrow">→</span>
  </a>
</div>

## Что уже выбрано за вас

Solo VPS предлагает один рекомендуемый путь и не заставляет собирать платформу из отдельных инструментов:

| Выбор | Для чего он нужен |
| --- | --- |
| **Ubuntu 24.04 LTS + Ansible** | Стабильная основа сервера и повторяемая настройка |
| **Защита SSH + UFW + обновления безопасности** | Практичная базовая защита хоста |
| **Docker + Coolify** | Контейнеры и панель для деплоев, доменов, HTTPS, переменных, баз данных и живых логов |
| **GitHub Actions + GHCR** | Проверка, сборка и деплой приложений после отправки кода в GitHub |
| **SOPS + age** | Зашифрованные инфраструктурные секреты и данные для восстановления |
| **restic, внешний мониторинг и Grafana Cloud** | Дополнительные внешние копии, уведомления о сбоях, история логов и метрики сервера |

Результат — не сложная multi-server платформа, а один понятный сервер с конкретными настройками и документированным восстановлением.

## Путь установки

Для настройки сервера используются несколько основных команд:

<div class="solo-command-path"><code>make setup</code><span>→</span><code>make apply</code><span>→</span><code>make secure</code><span>→</span><code>make platform</code><span>→</span><code>make verify</code></div>

[Быстрый старт](quick-start.md) объясняет, где выполняется каждая команда, что она меняет и какой результат считается успешным.

## Границы ответственности

| Область | Кто отвечает |
| --- | --- |
| Базовая настройка Ubuntu, SSH, firewall, Docker | **Solo VPS** |
| Деплой приложений и runtime configuration | **Coolify** |
| CI и публикация images, если включены | **GitHub Actions / GHCR** |
| Внешнее хранилище и сторонние аккаунты | **Вы** |
| Процедура восстановления | **Документация Solo VPS + ваши внешние credentials/backups** |

## Частые задачи

- **Новый сервер:** [Быстрый старт](quick-start.md)
- **Проблема до начала установки:** [Проверка окружения](preflight.md)
- **Развернуть приложение:** [Первое приложение](operations/first-app.md)
- **Найти деплои, переменные или текущие логи:** [Ежедневная работа](operations/operator-ui.md)
- **Понять, что настраивать после базы:** [После базовой настройки](operations/after-basic-setup.md)
- **Найти логи приложения за прошлые дни:** [История логов](operations/observability.md)
- **Проверить состояние хоста и bounded logs:** [Статус и логи](operations/status-and-logs.md)
- **Вынести резервные копии с VPS:** [Глава 6: внешние backup](operations/offsite-backups.md)
- **Сделать резервную копию PostgreSQL и проверить восстановление:** [Глава 4: backup и restore PostgreSQL](operations/postgresql-backups.md)
- **Получать уведомления о недоступности:** [Глава 5: внешний uptime-monitor](operations/external-uptime.md)
- **Следить за CPU, памятью и диском:** [Глава 7: метрики VPS](operations/metrics.md)
- **Разобрать сбой или подготовить обслуживание:** [Сбои и обслуживание](operations/incidents-and-maintenance.md)
- **Заменить потерянный VPS:** [Восстановление после потери VPS](disaster-recovery.md)
- **Обновить хост/платформу:** [Обновление Solo VPS и Coolify](upgrades.md)
- **Найти точную команду:** [Справочник команд](command-reference.md)
- **Понять ownership и границы системы:** [Архитектура](architecture.md)
