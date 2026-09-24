# Solo VPS Critic Review — Full

**Дата:** 2026-09-09

**Режим:** FULL

**Проверенная ревизия:** `1cb87465348a6ae752c7f7bf4302f1db472503a9`

**Вердикт:** REJECT как готовый кандидат для самостоятельного прохождения Quick Start новичком

**Максимальная подтверждённая критичность:** P1

**Область:** продукт, первый запуск, Ansible, безопасность, Coolify, CI/CD, эксплуатация, обновления, дополнительные профили, документация и проверяемость.

Это ревью текущего состояния, а не отчёт об исправлениях. Изменение в этой итерации — данный документ. Описанные ниже исправления ещё не реализованы.

## 1. Вывод

У проекта подходящее архитектурное ядро: Ansible управляет хостом, Coolify — приложениями и входящим HTTP/HTTPS, GitHub Actions — проверкой и сборкой, GHCR — образами. Возвращать Vault, Nomad, Consul, TeamCity, Nexus или отдельный proxy manager не нужно.

Сильнее всего сделаны защитные ограничения: поэтапное закрытие SSH, отдельные ключи человека и автоматизации, локальные management-порты, фиксация установочных артефактов, внешнее по отношению к checkout состояние, передача образа по digest. Слабее всего — соединение этих частей в один повторяемый пользовательский сценарий. Некоторые низкоуровневые операции аккуратны, но их основной Make-wrapper вызывает их в неподходящей фазе.

До тестирования на чистом VPS стоит исправить известные обрывы пути. Сейчас повторный `make platform` отвергает установленный Coolify; повторный `make apply` из оставленной bootstrap-сессии может отвергнуть уже переключённый inventory; установка после раннего сетевого сбоя не имеет полноценного продолжения; CI-шаблон запрещает домен из руководства первого приложения. Кроме того, зелёный `make verify` не означает, что установленный Coolify здоров.

**Правильная следующая итерация — сократить и замкнуть основной путь, затем проверить его на чистом VPS. Добавлять инфраструктурные компоненты сейчас не требуется.**

### Уточнённый продуктовый контракт

В этом ревью приоритет имеет актуальное требование владельца:

- Базовая установка не требует бэкапов, снапшотов, S3, Grafana Cloud или второго сервера.
- Локальные резервные копии могут быть дополнительной возможностью.
- Внешние копии и восстановление после потери VPS — отдельный дополнительный профиль.
- Разработчик получает понятный путь от пустого Ubuntu 24.04 до приложения, обновляемого через `git push`.

Это меняет приоритеты предыдущего ревью и ROADMAP. Отсутствие доказанного off-site restore больше не блокирует **тест базового профиля**. Однако локальная копия не переживает потерю VPS: базовый профиль не должен обещать восстановление данных после такой аварии. Можно предлагать платформу для production-развёртывания с явно описанными границами; нельзя приравнивать успешную установку к доказанной сохранности данных или высокой доступности.

## 2. Доказательства и ограничения

Прочитаны README, PROJECT_PASSPORT, ROADMAP, ключевые ADR и руководства по первому запуску, доступу, CI/GHCR, ENV, эксплуатации, observability, обновлениям, резервному копированию и восстановлению. Сопоставлены Makefile, основные lifecycle-скрипты, роли хоста/Coolify/CI transport, deployment API helper, workflow-шаблон и соответствующие тесты. Старый review использован как история, а не как доказательство актуального дефекта.

Глубина проверки различается: основной пользовательский путь и опасные переходы прочитаны по реализации; дополнительные подсистемы проверены по границам, ключевым операциям и тестам. Это не заявление о ручной проверке каждой строки всех переводов и legacy-материалов.

Среда ревью — Windows, без пригодного Linux/WSL-контроллера. Выполнены:

| Проверка | Результат | Что это доказывает |
|---|---|---|
| Git status и история | Исходное дерево чистое, локальная ветка `master`, HEAD указан выше | Файлы и коммиты доступны; рассматривается конкретная ревизия |
| Выбранные переносимые suites | **164 теста PASS**, 69,833 с | Работают проверенные Python/contract-сценарии; не заменяет Ubuntu/VPS |
| Полный `unittest discover` | **544 теста, 9 failures, 103 errors**, 130,602 с | Полный прогон в этой среде не зелёный |
| Разбор tracked YAML | **135 файлов PASS** | Синтаксический разбор с учётом Compose `!override`; не Ansible syntax-check/lint |
| Синтетический вызов deployment validator с доменом | **Воспроизведён отказ** | Подтверждает CRIT-024 без доступа к серверу/API |
| Три установочных файла Coolify v4.1.2 | **Все SHA-256 совпали** с defaults | Опубликованные исходные артефакты соответствуют pin; не проверяет Docker runtime |
| Поиск типовых сигнатур секретов в tracked-тексте | Кандидатов не найдено | Ограниченный поиск ключей/токенов; не полная проверка секретов в Git-истории |
| Реальные Ansible QA, SSH, Docker, Coolify, clean-VPS и GitHub Actions | **NOT RUN** | Нового runtime/release evidence в этой итерации нет |

В полном тестовом прогоне наблюдались Windows-ограничения: `pwd`/`geteuid`, POSIX-права, symlink privileges, Linux-пути, отсутствующие `make`/`python3`, разделители путей. Нельзя выдавать эти 112 отрицательных результатов за 112 дефектов Ubuntu-продукта. Нельзя и объявлять полный gate пройденным. Linux-проверка остаётся обязательной.

Переносимый набор охватил deployment API/image handoff, CI transport/template, Coolify install backend, lifecycle, Docker/firewall, README/documentation governance, state layout, hygiene, upgrades и QA contracts. Даже такой зелёный набор не поймал CRIT-021 и CRIT-024: основной пробел — проверки связанного сценария.

Измеренная поверхность tracked-исходников: 222 Make-цели; `scripts/` — 87 файлов / 17 439 строк; `tests/` — 55 / 7 540; `ansible/` — 139 / 7 968; `docs/` — 89 / 11 745; `legacy/` — 12 / 27 264. Сам размер не дефект, но это значительная стоимость сопровождения для обещания «несколько команд».

## 3. Блокирующие замечания — P1

Идентификаторы продолжают предыдущую серию CRIT-001…020. Оценка трудоёмкости: S — локальное изменение; M — несколько связанных компонентов; L — изменение сценария с runtime-проверкой. Это относительная оценка, не обещание сроков.

### CRIT-021 — Основной `platform` не идемпотентен

**Evidence:** `Makefile:385–388`, `ansible/roles/coolify/tasks/readiness.yml:118–145`, `ansible/playbooks/coolify.yml:15–57`.

`platform` всегда запускает `coolify-readiness`. Эта проверка требует свободных management-портов, отсутствия контейнера `coolify` и отсутствия данных предыдущей установки. Поэтому повтор после успешной установки заканчивается раньше, чем playbook сможет выбрать существующую managed-инсталляцию. В самом `coolify.yml` различение состояний уже предусмотрено.

**Исправить:** передать выбор first install / managed verify / interrupted install одному lifecycle-входу. First-install readiness должна выполняться только для действительно новой установки. Сохранить отказ от неявного захвата чужого Coolify.

**Приёмка:** `make platform` дважды на чистом VPS; второй запуск успешен, сохраняет секреты, приложения, ключи и pinned version. Отдельно проверить уже установленный чужой Coolify: понятный отказ без мутации.

**Уверенность:** высокая, прямой вывод из последовательности вызовов. **Объём:** S + VPS-проверка.

### CRIT-022 — Переход bootstrap → admin ломает обещание resume

**Evidence:** `scripts/operator_lifecycle.py:69–74,97–132`, `scripts/prepare_access.py:140–145`, `scripts/handoff_admin_workspace.py:225–232`, `Makefile:374–381`, `docs/quick-start.md:14,27–29,97–106`.

Два конкретных случая:

1. Первый `apply` переключил inventory на admin. Оператор повторяет команду из сохранённой root-сессии. Lifecycle пропускает bootstrap-переключение и вызывает `prepare-access`, требующий совпадения локального пользователя с `ansible_user`. Получается root против admin. Переданный `BOOTSTRAP_USER=root` тоже игнорируется, если inventory уже admin.
2. Руководство допускает provider-пользователя `ubuntu`, но команды установки пакетов показаны без `sudo`, а `secure` вызывает handoff без повышения привилегий. Handoff разрешает только retained root либо уже подготовленный admin workspace. Документированный `ubuntu`-путь до конца не соединён.

**Исправить:** явно моделировать пользователя текущего процесса, способ bootstrap-доступа и managed identity. Подготавливать admin workspace до перехода; использовать ограниченное повышение привилегий для нужного шага. Повтор после hardening не должен возвращать inventory на root. Синхронизировать изменённый host до запуска зависимых проверок. Если pre-alpha поддерживает только root-bootstrap, честно сузить Quick Start до него вместо заявления неподтверждённого второго пути.

**Приёмка:** первый/повторный apply из retained root, повтор из admin, остановка после переключения inventory, свежая сессия и продолжение; отдельный ubuntu-сценарий, если он остаётся заявлен. Ни один путь не требует ручного редактирования inventory для восстановления.

**Уверенность:** высокая по коду; live SSH не проверен. **Объём:** M.

### CRIT-023 — Interrupted install умеет принять готовый runtime, но не достроить ранний

**Evidence:** `ansible/roles/coolify/tasks/install.yml:29–89`, `ansible/playbooks/coolify.yml:25–47`, `ansible/roles/coolify/tasks/recover.yml:65–108,174–208`.

Pending-marker записывается до загрузки артефактов и создания секретов. Сбой сети после marker переводит следующий запуск в `recover`. Recovery требует уже существующих ключа, env, network и healthy runtime. При раннем сбое их ещё нет; этот путь не скачивает недостающее и не запускает установку. После устранения CRIT-021 такой partial state всё равно не продолжится обычной командой.

**Исправить:** восстановление установки по этапам с сохранением уже созданных секретов. Различать «артефакты не получены», «конфигурация подготовлена», «контейнеры запущены», «проверка завершена». Можно обойтись небольшим transaction manifest и идемпотентными задачами, без универсального workflow engine.

**Приёмка:** прервать установку после marker, после env, после SSH-key и после запуска контейнеров; восстановить сеть и повторить основной target. Установка завершается, идентичности не меняются, чужие данные не удаляются.

**Уверенность:** высокая по коду. **Объём:** M/L.

### CRIT-024 — CI-шаблон отклоняет публичный домен из first-app

**Evidence:** `scripts/coolify_deploy_api.py:189,227–228`, `templates/github-actions/hello-app-ci.yml:307–324`, `docs/operations/first-app.md:3`.

В helper `allow_domain=False` по умолчанию. Оба workflow-вызова, `--check` и `--apply`, не передают `--allow-domain`. Руководство создаёт приложение с `https://app.example.com`. Даже после перевода ресурса на Docker Image проверка остановится сообщением `isolated API proof requires an application with no public domain`.

**Исправить:** разделить ограничения изолированного эксперимента и рабочего deployment-профиля. Для обычного CI разрешить ожидаемый домен согласованно в check/apply, сохранив проверки resource UUID, image repository, digest и отсутствия host port mappings.

**Приёмка:** тест реальной конфигурации workflow + helper для приложения с доменом; deploy через HTTPS на тестовом VPS. Произвольная публикация порта контейнера по-прежнему отклоняется.

**Уверенность:** высокая, отказ воспроизведён локально. **Объём:** S.

### CRIT-025 — Первый образ и настройка CI требуют недокументированных решений

**Evidence:** `docs/operations/first-app.md:88–103,243–256`, `docs/ci-ghcr.md:33,111–154`, `scripts/coolify_deploy_api.py:244–256`, `Makefile` targets `check-ci-deploy-transport-confirm` / `ci-deploy-transport`.

Первое приложение собирается на VPS через Public Repository/Dockerfile. Следующий документ уже предполагает Docker Image resource с предыдущим immutable image. Не показан полный переход: первая публикация образа без работающего deploy, первоначальное здоровое развёртывание по digest, затем включение CD. Также не замкнуты настройка API, выбор публичного/private GHCR и pull credentials на стороне сервера. В примере параметры ключа переданы только `plan-ci-deploy-transport`; последующий `make ci-deploy-transport` их не наследует и требует ещё отдельного confirmation.

Официальное руководство Coolify отдельно требует включить API, создать token и настроить registry authentication. Публичный GHCR допускает anonymous pull, private — требует авторизации; GITHUB_TOKEN runner-а сам по себе не настраивает доступ VPS. Источники: [Coolify GitHub Actions](https://coolify.io/docs/applications/ci-cd/github/actions/), [GitHub Container registry](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).

**Исправить:** один first-app tutorial по желаемому пути Actions → GHCR → Coolify Docker Image. Явная фаза первого publish/deploy до активации автоматического rollback; копируемые команды transport с нужными параметрами; настройки GitHub/Coolify по шагам. Дать небольшой app starter с Dockerfile, healthcheck, ENV-примером, тестами и CI. Не заставлять пользователя сначала изучать альтернативную сборку на VPS.

**Приёмка:** человек без знания проекта проходит документ с пустыми app repo/GHCR/Coolify resource и получает второе развёртывание через push. Public и private image paths описаны отдельно; секреты не оказываются в репозитории или shell history.

**Уверенность:** высокая по несовпадению документов и preconditions. **Объём:** L.

### CRIT-026 — Старый успешный workflow может заменить более новый релиз

**Evidence:** `templates/github-actions/hello-app-ci.yml:213–215` и весь deploy job. Есть job concurrency с `cancel-in-progress: false`; проверки актуальности commit перед мутацией нет.

Пример: push A собирается долго, push B собирается быстро и уже развёрнут. Затем A доходит до deploy lock и развёртывается поверх B. Запрет одновременного выполнения не задаёт порядок по истории коммитов. GitHub также не обещает такой порядок: [workflow concurrency](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).

**Исправить:** определить политику «развёртывать актуальный main». Внутри deployment lock проверять, что кандидат ещё допустим относительно текущего main/последнего принятого релиза. Устаревший run должен закончиться без PATCH/POST. Сохранять последовательность мутаций; не обрывать активный rollout простой отменой job. Ручной rollback оформить как явную отдельную операцию.

**Приёмка:** искусственно задержать A, дать B развернуться, затем отпустить A. Итогом остаётся B; устаревший job не меняет desired state. Повторить с rerun старого workflow.

**Уверенность:** высокая по отсутствию freshness guard; гонка на live CI не запускалась. **Объём:** M.

### CRIT-027 — Основной verify не проверяет здоровье установленной платформы

**Evidence:** `Makefile:1041`, `ansible/playbooks/verify.yml:1–15`, `ansible/roles/platform_verify/tasks/main.yml:34–91`.

Aggregate запускает host-verifiers и диагностическую сводку. Он не включает `verify-coolify` и `verify-ssh`. Сводка показывает контейнеры и failed units, но не превращает остановленный Coolify в обязательный отказ. Поэтому возможен зелёный основной verify при неработающей установленной платформе. Сами специализированные проверки существуют.

**Исправить:** verify должен учитывать достигнутую фазу и включённые компоненты. До установки Coolify проверять baseline; после managed-marker обязательно проверять runtime Coolify; после secure — эффективный SSH contract. При проблеме возвращать ненулевой exit code и конкретный следующий шаг. Не делать optional backup/Alloy обязательными для core.

**Приёмка:** остановленный Coolify, unhealthy dependency и нарушенный SSH contract дают отказ соответствующей фазы; отсутствие ещё не установленного/не включённого компонента не даёт ложного отказа.

**Уверенность:** высокая по составу aggregate; отрицательный VPS-тест не выполнен. **Объём:** M.

### CRIT-028 — Optional off-site recovery фактически обязателен для update lifecycle

**Evidence:** `PROJECT_PASSPORT.md:343–357`, `ROADMAP.md:105–121,279–312`, `Makefile:417–425`, `docs/upgrades.md:103`, `scripts/coolify_database_backup_api.py:478`.

Базовый bootstrap действительно не устанавливает restic/Alloy — это уже правильно. Но критерии общего релиза требуют off-site/DB/lost-VPS proof, а Coolify upgrade безусловно вызывает `backup-check` для внешнего repository и требует отдельное off-site instance-DB confirmation. Пользователь без дополнительного профиля лишается поддержанного пути обновления. DB-helper также требует S3 UUID и не представляет local-only режим.

**Исправить:** развести готовность core и optional recovery. Для поддержанного обновления разработать локальный pre-upgrade checkpoint: конфигурация, нужный логический dump Coolify, manifest/version, закрытые права, проверка читаемости и описанный recovery. Это разовая защита операции, не обязательная фоновая backup-система. Проверки off-site выполнять при включённом профиле. Не убирать защиту обновления простым удалением `backup-check`.

**Приёмка:** сервер без S3/backup credentials проходит core install/verify и поддержанный upgrade с локальным checkpoint. Дополнительный off-site профиль отдельно доказывает restore; потеря VPS остаётся вне гарантий local-only.

**Уверенность:** высокая; приоритет обусловлен актуальным продуктовым требованием. **Объём:** M/L.

## 4. Существенные доработки — P2

### CRIT-029 — `make update` только показывает план; обслуживание версий не завершено

**Evidence:** `Makefile:402`, `docs/upgrades.md`, `ansible/roles/docker/tasks/main.yml`, `ansible/roles/updates/defaults/main.yml`, Coolify defaults/install.

Команда честно не меняет версии, Docker устанавливается с `state: present`, unattended origins ограничены Ubuntu, Coolify AUTOUPDATE отключён. Есть узкий переход Coolify 4.1.1 → 4.1.2. Полного пути «новый Solo VPS release → совместимый конфиг → Docker/Coolify security update → проверка» нет. Это нельзя называть автоматическим обслуживанием всей инфраструктуры.

**Действие/приёмка:** определить владельца обновлений каждого компонента, отдельные plan/apply и правила reboot; поддержанный upgrade не должен случайно устанавливать новый major. Добавить migration/version для persistent config и release matrix. На pre-alpha допустимо ограниченное ручное обновление по runbook, если это явно сказано. Проверить один реальный поддержанный переход и прерывание операции. **Уверенность:** высокая. **Объём:** M/L.

### CRIT-030 — Передача confirmation через sudo в optional restore ненадёжна

**Evidence:** `Makefile:843`, `scripts/coolify_instance_restore.py:381–382`.

Make передаёт `SOLO_VPS_DISASTER_RECOVERY_CONFIRM=...` в окружение команды `sudo -n python ...`. При стандартном `env_reset` переменная не обязана попасть в Python, а скрипт требует её точного значения. Вывод основан на коде и [официальном описании sudo](https://github.com/sudo-project/sudo/blob/main/docs/UPGRADE.md); на целевом Ubuntu этот путь не воспроизводился.

**Действие/приёмка:** передать именно это несекретное подтверждение после sudo либо структурированным аргументом. Не включать глобальный `sudo -E`. Проверить под обычным sudo-admin: отсутствие/неверное подтверждение отвергается, верное проходит validation до restore. **Уверенность:** высокая для стандартного sudo policy, target-specific поведение не проверено. **Объём:** S. Блокирует optional restore, а не тест core.

### CRIT-031 — Полный developer QA встроен в обычную установку и SSH-handoff

**Evidence:** `Makefile:338–341,602–608`, `tools/qa-requirements.txt`, `scripts/handoff_admin_workspace.py:248–251`.

`setup` устанавливает не только Ansible runtime, но и ansible-lint/yamllint. Handoff заново делает admin setup, полный `make validate`, prepare-access и doctor. Так обычный security transition зависит от повторной установки toolchain, сети и большого набора source-contract tests. Работа продублирована между root/admin состояниями.

**Действие/приёмка:** разделить минимальный runtime controller и developer/release QA; сохранить проверки конфигурации, доступности ключей, совместимости и SSH непосредственно на VPS. Admin workspace подготовить до критического перехода. Повторное setup должно проверять уже готовый pinned runtime без обязательного pip-download; полный lint/test оставить в repo CI. **Уверенность:** высокая. **Объём:** M.

### CRIT-032 — Ресурсные ограничения обнаруживаются поздно; ежедневные сигналы неполны

**Evidence:** `ansible/roles/coolify/tasks/readiness.yml`, `ansible/roles/preflight/tasks/main.yml`, `docs/quick-start.md`, `docs/operations/observability.md`, `docs/operations/status-and-logs.md`.

Проверки 2 vCPU / 2 GiB RAM / 30 GiB свободного места появляются на этапе платформы, уже после host setup и SSH transition. Новичок мог выбрать слишком маленький VPS. Log rotation есть, но она не ограничивает объём образов, volumes, БД и всех данных Coolify. Локальные status/verify полезны по запросу; полный metrics/alerting path ещё не автоматизирован.

**Действие/приёмка:** показать минимумы и запас на приложения до аренды; проверить ресурсы до первой существенной мутации. Для core дать понятные disk/reboot/failed-unit/container-health сигналы и безопасный runbook очистки. Не запускать общий автоматический `docker system prune --volumes`. Внешний uptime — простой рекомендованный optional сервис. Официальные минимумы Coolify: [installation](https://coolify.io/docs/get-started/installation); они не гарантируют достаточность для приложений пользователя. **Уверенность:** высокая. **Объём:** M.

### CRIT-033 — Public release и repository CI ещё не соединены с фактической веткой

**Evidence:** локальный Git — `master`, без remote и tags; `.github/workflows/repository-ci.yml:4–8`, `.github/workflows/docs.yml:12–15`, `SECURITY.md`, `.github/dependabot.yml`.

Push-workflows настроены на `main`. Если опубликовать текущую `master` без согласования, push-gates не запустятся; PR/workflow_dispatch — другие пути. Отсутствие remote здесь не доказывает отсутствие репозитория где-либо, но не позволяет подтвердить hosted runs, protection и security reporting. README не даёт установленную релизную точку входа. Dependabot охватывает только Docker reference app; docs workflow использует version tags actions, тогда как deployment template закрепляет SHA.

**Действие/приёмка:** при подготовке публичной alpha согласовать default branch и workflow filters, получить настоящий hosted run на публикуемой ревизии, настроить required checks и private security reporting, выпустить immutable tag. Проверять обновления runtime/QA/actions по единой политике. До этого использовать проверенный commit для тестов. **Уверенность:** высокая для локального snapshot, hosted settings неизвестны. **Объём:** M.

### CRIT-034 — Documentation/contract machinery подменяет проверку пользовательского пути

**Evidence:** 164 зелёных tests при CRIT-021/024; `Makefile` validate targets; `docs/testing.md`, `docs/clean-vps-test.md`, ROADMAP; `Makefile:25,269–270`.

Документация смешивает tutorial, ограничения реализации и дневник M-итераций. First-app и CI описывают разные стартовые модели. Clean-VPS runbook включает maintainer-команды и не заменяет самостоятельное прохождение публичных пяти этапов. Значительная часть guards проверяет наличие строк и маркеров, а не результат связанного вызова. Отдельное исключение из обещания «ничего в checkout»: developer docs tooling создаёт `.venv-docs`/`site`, хотя operator state вынесен наружу.

**Действие/приёмка:** один короткий public tutorial, operations по задачам, reference отдельно, историческое evidence в review/history. Добавить несколько тестов реальных переходов вместо новых валидаторов формулировок. Runtime-путь проверить с неизменным tracked tree и без новых файлов в checkout; developer-output вынести либо явно ограничить соответствующим режимом. **Уверенность:** высокая. **Объём:** M, удаление лишних guards — постепенно.

## 5. Что сделано хорошо и что сохранить

| Решение | Польза | Что проверить или ограничить |
|---|---|---|
| Ansible владеет OS/Docker, Coolify — apps/proxy | Понятное разделение ответственности | Не создавать второй независимый reverse proxy |
| Additive admin keys и staged SSH hardening | Снижает вероятность потери доступа | Доказать переход и повторение в root/ubuntu сценариях |
| Проверка sshd до reload, свежая сессия, provider recovery | Защищает наиболее опасный шаг | Подтверждения сохранить; улучшить формулировки и исполнение |
| Management 8000/6001/6002 на loopback | Уменьшает внешнюю поверхность | Проверить фактическую публикацию по IPv4 и IPv6 |
| Отдельный CI forwarding-only account | CI SSH-key не даёт обычную shell/sudo/Docker сессию | Coolify API token всё равно привилегирован; документировать scope/rotation |
| Immutable application image и fresh-runner smoke test | Проверяется именно опубликованный артефакт | Связать runtime version/health с этим digest и добавить freshness policy |
| Разделение image rollback и DB/schema recovery | Нет ложного обещания откатить данные сменой контейнера | Проверить timeout, concurrent UI deploy и нездоровый previous image |
| Persistent state вне source checkout | Основа безопасного reclone/update | Упростить единственного владельца state после handoff |
| Log rotation и Coolify live logs | Полезная локальная диагностика без отдельного сервиса | Это не полный disk budget и не alerting |
| Optional роли не входят в bootstrap | На базовом сервере уже нет ненужного restic/Alloy | Довести эту границу до upgrades, docs и release gates |

UFW нельзя считать достаточной защитой опубликованных Docker-портов: Docker перенаправляет такой трафик до обычных UFW input rules. Проект правильно выделяет этот риск и проверяет публикации. Сохранить эту практику, а не заменять её красивым `ufw status`. Источник: [Docker packet filtering and firewalls](https://docs.docker.com/engine/network/packet-filtering-firewalls/).

Coolify с passwordless sudo и Docker контролирует хост с полномочиями уровня root, даже если SSH-login называется иначе. Это удобная административная граница, не изоляция недоверенных tenants. Официально non-root setup отмечен экспериментальным: [Coolify non-root user](https://coolify.io/docs/knowledge-base/server/non-root-user). Для pre-alpha оставить выбранный путь и доказать его, а не спешно менять backend.

## 6. Вердикт по технологиям и составу продукта

| Технология / подсистема | Вердикт | Ценность, стоимость и основной риск |
|---|---|---|
| Ansible | KEEP | Подходящий idempotent host manager. Нужен небольшой runtime; весь developer QA на VPS не нужен |
| Make | KEEP / REVISE | Уже объединяет команды. Оставить пять основных этапов; 222 внутренние цели не должны быть учебной программой пользователя |
| Docker | KEEP | Основа Coolify/apps. Нужны version policy, disk budget и явное понимание published ports |
| Coolify | KEEP / REVISE | UI для ENV, ресурсов, deploy и live logs. Собственный manual installer требует сопровождать upstream schema/compose/non-root совместимость |
| GitHub Actions | KEEP | Сборка и тесты вне малого VPS. Starter должен демонстрировать test + lint/format-check + build + deploy; сейчас app workflow в основном показывает unittest |
| GHCR | KEEP | Естественный registry рядом с GitHub. Требуются понятные первый publish, digest и public/private pull paths |
| Coolify API helper | REVISE | Даёт bounded deployment/rollback. Не развивать в универсальную копию Coolify CLI; устранить изолированные proof-ограничения и гонки |
| Grafana Cloud + Alloy | OPTIONAL | Исторический поиск логов без локального Loki. Дополнительные credentials/стоимость/лимиты; убрать из обязательного onboarding |
| Self-hosted Grafana/Loki | DEFER | Возможное расширение, но потребляет память/диск и само требует обслуживания. Добавлять по измеренному ресурсу и спросу |
| SOPS/age | OPTIONAL, workstation | Полезно для дополнительных инфраструктурных секретов. Обычные app ENV пользователь вводит в Coolify; не нужен обязательный крипто-bootstrap для core |
| restic + external storage | OPTIONAL | Подходит для off-site recovery material. Не должен быть условием простой установки и единственным способом обновить core |
| Coolify-native DB backup | OPTIONAL | Сохраняет одного владельца DB backup. Предусмотреть local-only отдельно от S3; не копировать работающий raw PGDATA как portable backup |
| External uptime | OPTIONAL, рекомендовать | Может заметить недоступный единственный VPS. Не требует второго управляемого пользователем сервера |
| Error tracking / Sentry | OPTIONAL, позже | Полезно на уровне приложения; добавить инструкцию SDK/ENV, а не тяжёлую self-hosted установку в baseline |
| Vault/Nomad/Consul/TeamCity/Nexus/GitLab/NPM | НЕ ДОБАВЛЯТЬ | Для данного single-VPS продукта дублируют выбранных владельцев или значительно увеличивают эксплуатацию |
| Отдельный Dozzle | НЕ ДОБАВЛЯТЬ в core | Live logs уже даёт Coolify; ещё один UI/порт/auth сейчас не закрывает главный пробел |

Pin трёх файлов Coolify v4.1.2 проверен, но это не означает полную воспроизводимость всех runtime images и отсутствие уязвимостей. При обновлении нужны release/security review, совместимость и VPS-проверка. Одна лишь дата advisory после даты релиза не доказывает уязвимость используемой версии: например, проверенный [GHSA-chg4-63hm-xv9x](https://github.com/coollabsio/coolify/security/advisories/GHSA-chg4-63hm-xv9x) указывает affected range beta.471–beta.473 и исправление beta.474, а не 4.1.2. В этом ревью подтверждённый P0 не установлен; полного аудита всех upstream dependencies не выполнялось.

### Что перестроить в документации

Публичная навигация должна отвечать на задачи человека:

1. «Установить Solo VPS» — один основной сценарий, один config, понятные workstation/VPS контексты.
2. «Развернуть первое приложение» — GitHub → GHCR → Docker Image → HTTPS.
3. «Работать каждый день» — ENV, deploy, CI logs, application logs, restart, health, disk, rollback.
4. «Обновить платформу» — поддержанные версии, plan/apply, checkpoint, проверка, прерывание.
5. «Подключить дополнения» — local backup, off-site recovery, historical logs, monitoring.
6. «Reference / troubleshooting» — детали и внутренние targets по необходимости.

M-номера, выдержки прошлых экспериментов и доказательства maintained-host нужны maintainer-у. Их следует вынести из обычной инструкции в developer/evidence раздел. `legacy/` убрать из пользовательского маршрута и будущего runtime-пакета; Git-историю удалять не требуется. Не начинать ещё одну переработку темы сайта до исправления командного пути.

## 7. Как должен начинать пользователь

### Для pre-alpha — git clone конкретной ревизии

Оставить checkout как способ доставки. Он уже работает с внешним state и даёт прозрачные код, diff и revision. Новый curl-installer, пакетный менеджер и глобальная CLI-обёртка сейчас расширят число непроверенных путей.

Source-only означает: operator-команды читают файлы checkout, конфиг/ключи/toolchain/evidence пишут вне него, runtime живёт в предназначенных системных каталогах. Это не запрет разработчику редактировать исходники. Основной контракт надо проверять не только `git status`: ignored-файлы тоже являются записями в checkout.

В перспективе возможен компактный versioned archive и небольшая команда `solo-vps`, вызывающая существующую логику. Делать это после стабильного сценария, без второй реализации Ansible orchestration.

### Предлагаемый первый маршрут после исправлений

Это целевой UX, **не новая инструкция, уже доказанная на текущей ревизии**. `<repository-url>` и `<tested-revision>` — placeholders: фактический remote/tag в проверяемой копии не настроен.

**До VPS:** пользователь имеет GitHub account, ключ SSH на своём компьютере, доступ к DNS и provider console. Требования к RAM/CPU/free disk видны до аренды. В руководстве один выбранный bootstrap-вариант; альтернативный provider user — отдельная проверенная ветка инструкции.

**Первый SSH-вход на VPS с root-доступом:**

```bash
apt-get update
apt-get install -y --no-install-recommends git make
git clone <repository-url> solo-vps
cd solo-vps
git checkout --detach <tested-revision>
make setup
make paths
```

`setup` должен поставить минимальные зависимости и показать следующий шаг. Пользователь заполняет host, hostname, admin user и публичный workstation key в одном понятном месте. Приватный workstation key остаётся на компьютере. Текущий helper загрузки публичного ключа можно сохранить, но команда и её контекст должны быть прямо в tutorial.

Затем:

```bash
make apply
```

Ожидаемый результат: host baseline применён, admin workspace готов, показана точная команда нового входа. В свежем терминале компьютера пользователь подтверждает `ssh <admin>@<server>` и `sudo -n id -u`; проверяет provider recovery. После реального подтверждения выполняет документированный `make secure`, затем переподключается как admin:

```bash
cd ~/solo-vps
make platform
make verify
```

Подтверждения SSH не убирать ради числа команд: это осмысленная защита от потери доступа. Но вывод должен объяснять их обычными словами. Итого пять основных lifecycle-этапов: setup, apply, secure, platform, verify; операции clone/config/SSH/UI неизбежны и должны быть честно показаны.

**Coolify UI:** открыть туннель одной копируемой командой с локального компьютера, зарегистрировать администратора, проверить сервер/proxy. UI/API остаются закрытыми снаружи. Затем tutorial ведёт через первый immutable image и Docker Image resource, домен/TLS, healthcheck и runtime ENV.

**GitHub:** маленький starter либо готовый комплект файлов для своего приложения; production environment, необходимые variables/secrets, restricted deploy key и host key, включённый Coolify API, credentials для выбранного registry mode. Сначала получить первый здоровый digest, затем активировать CD с детерминированным rollback target.

**Первая полезная проверка:** изменить видимую версию приложения, commit/push, увидеть checks/build/publish/deploy и новую версию по HTTPS. Показать, где CI build logs, где deployment logs, где application logs и где менять ENV. Изменение ENV должно иметь понятный шаг restart/redeploy и проверяемый результат. Не выводить секреты в sample response/logs.

**Следующая проверка:** намеренно плохой healthcheck оставляет CI красным и возвращает предыдущий контейнерный релиз. Пользователь видит границу: image rollback не откатывает миграции/данные и не является автоматическим исправлением любой будущей ошибки приложения.

## 8. Проверка продуктового обещания

Статусы ниже — оценка по исходникам и выполненным локальным проверкам. Ни один PARTIAL не означает свежий live PASS на VPS.

| Шаг | Статус | Основание |
|---|---|---|
| Получить Solo VPS | PARTIAL | Checkout предполагается готовым; публичная версия/точная clone-точка входа не завершены |
| Пройти Quick Start без знания проекта | FAIL | Identity/handoff и скрытые предпосылки |
| Подготовить Ubuntu 24.04 | PARTIAL | Хорошие роли baseline, новый clean-host proof отсутствует |
| Повторить несколько основных команд | FAIL | CRIT-021/022/023 |
| Завершить ручные UI-настройки | PARTIAL | Coolify-first-app есть, переход в CI требует догадок; Grafana optional |
| Деплоить sample через push | FAIL | Domain guard и начальное immutable state |
| Смотреть CI build logs | PARTIAL | GitHub workflow предусмотрен, end-to-end новый run не выполнен |
| Смотреть deployment/live app logs | PARTIAL | Coolify/runbooks подходят; runtime не проверен в этой итерации |
| Искать исторические логи | PARTIAL, optional | Alloy/Grafana профиль; не core dependency |
| Проверять host/app health | PARTIAL | Специализированные checks есть, aggregate неполон |
| Получать внешний сигнал о падении | PARTIAL, optional | Provider-neutral инструкция; реальный alert не доказан здесь |
| Восстановиться после плохого релиза | PARTIAL | Bounded image rollback есть, race/timeout/previous-health требуют проверки |
| Восстановиться после потери VPS | NOT TESTED, optional | В core отсутствует по выбранному контракту; off-site профиль не доказан здесь |
| Обновить Solo VPS/инфраструктуру | PARTIAL | План и один Coolify transition, нет завершённого core lifecycle |

Оценка «30–60 минут до результата» пока не измерена. Замерять от первого входа до второго успешного push-deploy, включая ручные UI-шаги и время поиска ответов в документации. Не измерять только время Ansible playbook.

## 9. Scorecard

Шкала: 0 — отсутствует/небезопасно, 1 — основной путь сломан, 2 — слабое место, 3 — применимо с существенными ограничениями, 4 — сильная реализация, 5 — отлично и доказано. Это качественная оценка проверенной ревизии, не средний балл для допуска релиза.

| Область | 0–5 | Причина |
|---|---:|---|
| Quick Start / onboarding | 2 | Пропуски получения source и переходов пользователя |
| CLI / Make UX | 2 | Пять основных имён есть, повторение нарушено |
| Configuration UX | 3 | Один config и external state; ручной bootstrap/handoff усложняют |
| Dependency/bootstrap UX | 2 | QA toolchain и повторная подготовка попали в runtime |
| Architecture simplicity | 3 | Небольшой runtime, слишком большая orchestration/contract поверхность |
| Security | 3 | Хорошие защитные решения; clean-host/negative evidence ещё нужен |
| CI/CD | 2 | Правильные стадии, разрыв first app → CI |
| Deployment correctness | 2 | Immutable digest, но domain blocker и stale-run race |
| Rollback/recovery | 2 | Image recovery есть; исходное здоровье и concurrency требуют доказательства |
| Logging | 3 | Local rotation/live logs; optional history |
| Metrics/alerting | 2 | Диагностика и планы есть, полный простой сигнал не замкнут |
| Error tracking | N/A | Осознанно вне core; будущая app-интеграция |
| Backup/restore | 2 optional / N/A core | Объёмная реализация, off-site evidence отсутствует, local-only UX не завершён |
| Upgradeability | 2 | Узкий Coolify transition с обязательным off-site gate |
| Documentation | 3 | Много полезного содержания, несколько несовместимых happy paths |
| Testing/evidence | 2 | Много contracts, недостаточно связанных runtime/negative сценариев |
| Public repository hygiene | 3 | External state и проверки; publication/security channel не подтверждены |
| Daily operations UI/UX | 3 | Coolify покрывает основные действия; verify/update ещё требуют знаний |

## 10. Пять изменений с наибольшей пользой

| Порядок | Работа | Результат, который нужно предъявить |
|---|---|---|
| 1 | Закрепить новый core/optional контракт в Passport, ROADMAP и docs | Ни один core gate не требует S3/Grafana/DB backup; границы сохранности данных честны |
| 2 | Исправить lifecycle: apply/handoff, platform, interrupted install, phase-aware verify | Первый запуск, повтор и продолжение с нескольких контрольных точек проходят без ручного ремонта |
| 3 | Замкнуть первый app CI: initial image, domain, transport, ENV, freshness | Два push-deploy и отказ плохого/устаревшего candidate на реальном тестовом приложении |
| 4 | Разделить runtime/developer tooling и завершить ограниченный update runbook | Нет полного source QA во время SSH transition; core update не требует external storage |
| 5 | Провести буквальный clean-VPS проход и оформить проверенную ревизию | Короткое обезличенное evidence с командами, исходами и оставшимися ограничениями |

Не требуется делать все P2 до первого инженерного теста. P1 основного пути, минимальные инструкции и проверка ресурсов — первый пакет. Поддержанный update/checkpoint можно проверять следующей отдельной сессией, но тогда pre-alpha release notes должны явно ограничить проверенную область первой установкой. До обещания самоуправляемой production-инфраструктуры lifecycle обновления обязательно закрыть.

## 11. Приёмка перед передачей на чистый VPS и во время теста

### До первой установки

- Исправлены CRIT-021…027 либо явным scope-решением убран неподдержанный bootstrap-вариант CRIT-022.
- Quick Start действительно начинается с получения конкретной ревизии и проверки ресурсов.
- Выполнены Linux source/Ansible gates; Windows smoke не записан вместо них.
- Core не запрашивает S3/Grafana/backup credentials. Неиспользуемые optional пакеты и services не устанавливаются.
- Фиксируются только безопасные source/example/review файлы; runtime dumps, evidence с адресами/UUID и ключи остаются вне Git.

### Матрица реального прогона

| Сценарий | Ожидаемое доказательство |
|---|---|
| Root-bootstrap; ubuntu-bootstrap, если заявлен | Все шаги публичного документа без недокументированных исправлений |
| `apply`/`platform` повторно | Успех, сохранение идентичностей/секретов, нет лишней смены сервисов |
| Прерывание install и SSH/admin перехода | Понятное продолжение; без удаления `/data/coolify` и регенерации существующих секретов |
| Reboot VPS | Приложение, proxy и управление возвращаются; verify отражает фактическое состояние |
| Внешняя проверка портов, IPv4/IPv6 | Только предусмотренные SSH/HTTP/HTTPS; management/DB/app internal ports закрыты |
| Stop/unhealthy Coolify, нарушенный SSH contract | Основной verify возвращает ошибку нужной фазы и полезную диагностику |
| First image → second push → ENV change | Проверенный digest/видимая версия, правильные логи и применение runtime ENV |
| Broken healthcheck / stale older workflow | Возврат предыдущего container release / отсутствие мутации старым run |
| Таймаут candidate, ручной deploy во время CI, unhealthy previous | Явная безопасная политика; отсутствие ложного «known-good rollback» |
| Read-only/неизменный checkout | Operator state и generated files отсутствуют в source; после reclone конфигурация пригодна |
| Core upgrade без S3, отдельный от install тест | Проверенный локальный checkpoint, supported transition и failure/resume semantics |

Последние deployment edge cases — пробел доказательств, а не уже воспроизведённые отдельные P1. Например, `capture_previous_image_state()` читает предыдущий **desired** digest, не доказывая его живое здоровье, а timeout candidate сразу запускает rollback. Надо проверить поведение Coolify при ещё активном candidate прежде, чем расширять обещание автоматического восстановления.

Optional acceptance ведётся отдельно: local DB backup/restore; restic + S3 restore; потеря VPS и восстановление; Alloy ingestion/сокрытие секретов; настоящий внешний alert. Не задерживать тест core отсутствием этих профилей и не ставить им PASS по наличию исходников.

## 12. Что сейчас не строить

Не добавлять второй orchestrator, Kubernetes/multi-node, собственный web dashboard, автоматизацию всех экранов Coolify, universal DB migration executor, self-hosted observability suite и новый installer/package format. Не расширять support matrix несколькими ОС/дистрибутивами. Не писать ещё десятки валидаторов наличия слов в документах.

После доказанного pre-alpha пути разумные расширения: local backup profile, off-site recovery profile, готовый app starter/template, versioned update с config migration, небольшая ENV/health/logs диагностика, optional hosted error tracking, затем self-hosted Grafana по реальному спросу и ресурсному бюджету.

**Итог:** проект стоит продолжать на выбранном стеке. До пользовательского теста нужно исправить стыки основного сценария; до публичной alpha — предъявить clean-VPS и hosted CI evidence. Главная работа сейчас — сделать существующие действия повторяемыми и понятными. Отсутствие внешних бэкапов в базовой версии соответствует новому контракту и само по себе не является основанием отклонять core.
