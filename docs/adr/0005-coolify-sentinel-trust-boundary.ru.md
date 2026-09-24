# ADR-0005: Принимать Coolify Sentinel только внутри границы доверия Coolify

Статус: Предложено

Дата: 2026-09-17

## Контекст

Coolify `4.3.19` сделал Sentinel обязательным для обычных серверов. Sentinel передаёт в Coolify состояние хоста и контейнеров и при необходимости хранит историю CPU/RAM. Upstream-контейнер использует host PID namespace и Docker socket в режиме read-write, поэтому это привилегированная часть control plane, а не изолированный metrics sidecar.

Solo VPS держит management ports Coolify только на loopback. Поэтому сгенерированный localhost URL Sentinel `http://host.docker.internal:8000` не может быть поддерживаемым путём связи: публикация raw port `8000` ослабила бы существующую границу.

## Предлагаемое решение

Считать Sentinel частью уже существующего high-trust control plane Coolify, а не отдельным low-trust компонентом мониторинга.

Принимать требующую Sentinel версию Coolify только после того, как испытание на disposable VPS докажет всё перечисленное:

- Sentinel отправляет данные на существующий публичный HTTPS URL панели Coolify со сгенерированным authentication token;
- Sentinel API не публикуется на хосте;
- raw management ports Coolify остаются loopback-only;
- debug mode выключен, а точные image/version известны;
- host PID и read-write доступ к Docker socket соответствуют явно проверенному upstream contract;
- backup, recovery, verification и audit продолжают работать.

Сбор metrics остаётся опциональным. Repository-managed Alloy остаётся отдельным поддерживаемым путём retained logs и host metrics.

## Последствия

Компрометацию Sentinel нужно считать компрометацией control plane Coolify, потому что Docker socket позволяет управлять контейнерами хоста. Этот компонент нельзя честно называть least-privilege или read-only.

HTTPS push path не открывает новый management port, но зависит от доступности dashboard domain, TLS и reverse proxy. Поэтому disposable evaluation должен доказать связь до и после обновления.

Пока испытание кандидата не пройдено, Solo VPS сохраняет прежние поддерживаемые pins Coolify. Это предложение не разрешает автоматическое обновление или recovery через downgrade.
