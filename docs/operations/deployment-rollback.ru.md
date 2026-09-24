# Восстановление после неудачного деплоя приложения

Deployment helper Solo VPS добавляет одну узкую safety transaction вокруг immutable Docker Image updates в Coolify. Если candidate deployment падает или становится unhealthy, helper может восстановить **предыдущий container image**.

Он не откатывает базы данных или внешние side effects.

## Обычный deployment path

```text
git push
→ Application tests
→ Application migration preflight
→ build/publish immutable image to GHCR
→ Coolify deploys exact digest
→ health verification
```

До mutation helper сохраняет текущий immutable desired image. Если candidate падает после update, helper возвращает предыдущий immutable image, запускает его и требует, чтобы приложение снова стало `running:healthy`.

Failed candidate всё равно оставляет CI красным. Rollback восстанавливает service state, но не превращает неудачный release в успешный.

## Классы результата

```text
DEPLOY_FAILED_ROLLBACK_OK
```

Candidate failed, но предыдущий exact image восстановлен и стал healthy.

```text
DEPLOY_FAILED_ROLLBACK_FAILED
```

Candidate failed, и автоматическое восстановление также не удалось. Используйте напечатанный known-good recovery path и Coolify UI для расследования.

Helper отказывается использовать mutable previous image вроде `latest`; rollback authority требует immutable digest.

## Граница database migration

Scope rollback — **только container image**.

Он не обращает назад:

- изменения database schema;
- mutations application data;
- external API side effects;
- queue/event side effects.

Для schema changes предпочитайте backward-compatible **expand-contract** migrations, пока previous image остаётся deployable. Для irreversible migration нужен реальный backup/restore или forward-fix plan до deployment.

Обязательный **Application migration preflight** не изменяет данные и не получает production deployment credentials. Этот hook принадлежит приложению; Solo VPS не делает вид, что понимает произвольные schemas.

## Если автоматический rollback не удался

Оставляйте Coolify port `8000` приватным. Используйте локальный/restricted deployment-control path, который печатает helper, или штатный UI Coolify.

После recovery:

```bash
make verify-coolify
make audit
```

Затем подтвердите intended immutable image и application health в Coolify.

## Связанные страницы

- [GitHub Actions + GHCR](../ci-ghcr.md)
- [Backup PostgreSQL](../database-backups.md)

Перед изменением helper требует `running:healthy` и immutable desired digest. При неизвестном исходе, ошибке API или таймауте исходного deploy автоматический rollback не запускается: он мог бы пересечься с ещё выполняющимся деплоем. Проверьте историю Coolify и завершение операции, прежде чем действовать вручную. Статус health и desired digest сами по себе не доказывают отсутствие ручного drift контейнера; не совмещайте CI и ручные деплои.
