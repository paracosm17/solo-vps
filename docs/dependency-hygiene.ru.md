# Гигиена обновления зависимостей и образов

M12 задаёт небольшой update contract для зависимостей, которые уже существуют в проекте. Он не добавляет vulnerability scanners, генераторы SBOM, signing или автоматический merge.

## Текущие классы зависимостей

| Зависимость | Текущая политика | Путь обновления |
| --- | --- | --- |
| `python:3.13.14-slim-bookworm` | точный Python patch tag, Debian variant зафиксирован | еженедельный Dependabot PR для `examples/hello-app/Dockerfile` |
| `community.general` | точная версия collection `13.0.1` | ручное reviewed изменение зависимости |
| GitHub Actions в `templates/github-actions/hello-app-ci.yml` | pins по полному commit SHA | ручное reviewed изменение зависимости |

Validator этой политики — `scripts/validate_dependency_hygiene.py`; он входит в `make validate`.

## Почему sample base image закреплён patch-tag, а не digest

Финальная deployable identity sample-приложения уже является immutable digest GHCR image, который выдаёт M11. У base image другой trade-off.

В этом slice Dockerfile использует:

```dockerfile
FROM python:3.13.14-slim-bookworm
```

вместо плавающего minor tag вроде `python:3.13-slim-bookworm`. Благодаря этому изменения Python maintenance version становятся явными в review.

При этом `@sha256:...` пока намеренно **не** добавляется. Текущее поведение Dependabot Core подавляет Docker digest-only updates, если версия tag не изменилась. Поэтому точный digest мог бы заморозить same-tag rebuilds официального Python image, если проект не добавит отдельный механизм обновления digest.

Оба M11 Buildx step используют `pull: true`, поэтому hosted builds явно пытаются обновить referenced base images. Итоговый application image всё равно адресуется registry digest при deployment.

Если позже проект примет инструмент, который надёжно предлагает digest refresh, переход base image на `tag@sha256:digest` можно пересмотреть как отдельное изменение dependency policy.

## Scope Dependabot

`.github/dependabot.yml` сейчас содержит один updater:

```text
Docker ecosystem
→ /examples/hello-app
→ weekly
→ только patch updates внутри текущей Python feature series
→ не более двух открытых version-update PR
```

Major/minor обновления Python feature series игнорируются автоматизацией и должны review-иться как отдельное dependency change. Auto-merge policy и registry credential configuration отсутствуют.

Проект намеренно **не** утверждает, что этот Dependabot file поддерживает action pins из `templates/github-actions/`. GitHub `github-actions` updater Dependabot находит workflow dependencies в `.github/workflows` при `directory: "/"`; текущий файл — copyable template, который лежит в другом месте.

Когда application repository копирует template в `.github/workflows/ci.yml`, этот repository может добавить собственный `github-actions` Dependabot entry. Для текущего source project action pins остаются ручным reviewed update, пока их размещение/tooling не будет изменено намеренно.

## Политика Ansible collection

`community.general` — единственная внешняя Ansible collection, которая сейчас обязательна. Она pin-ится точно в `ansible/requirements.yml`:

```yaml
collections:
  - name: community.general
    version: "13.0.1"
```

Точный pin делает `make deps` воспроизводимым относительно этой collection. Dependabot сейчас не перечисляет Ansible Galaxy как поддерживаемый package ecosystem, поэтому upgrades collection остаются ручными:

```text
review upstream release notes
→ обновить точную версию
→ make deps в disposable/controller environment
→ make validate
→ ansible syntax/integration checks, когда доступны
```

Добавление ещё одной обязательной collection требует намеренно обновить dependency contract, а не незаметно расширять `requirements.yml`.

## Что отложено

Этот slice не добавляет:

- vulnerability scanning gates;
- SBOM/provenance attestations;
- image signing;
- автоматизацию image retention;
- автоматический dependency merge.

Эти функции добавляют CI cost и policy surface и должны появляться только при понятной failure/maintenance model. Они остаются P2 follow-up work и не должны задерживать всё ещё заблокированный P1 deployment path.

## Проверка

Запустите:

```bash
make validate-dependency-hygiene
make validate
```

Локальная validation проверяет, что:

- Dependabot нацелен только на sample Dockerfile с weekly patch-only schedule;
- registry credential block или unrelated ecosystem не добавлены;
- sample base image использует точный Python patch tag `X.Y.Z` и фиксированный variant `slim-bookworm`;
- текущий slice не вводит незаметно digest pin без соответствующей update strategy;
- внешняя Ansible collection закреплена точной версией;
- M11 builds сохраняют `pull: true` через существующий CI-template validator.

Настоящий Dependabot PR — GitHub-hosted behavior и не доказывается одной только локальной validation.
