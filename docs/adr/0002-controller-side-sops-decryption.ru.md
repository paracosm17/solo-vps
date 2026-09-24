# ADR-0002: Хранить приватный SOPS age-ключ на рабочей станции оператора

Статус: Принято  
Дата: 2026-08-11  
Упрощено: 2026-08-14

## Контекст

У Solo VPS один production VPS. У пользователя естественным образом есть домашний/рабочий компьютер, с которого он администрирует сервер. Эта рабочая станция может быть Windows или Linux; это **не второй сервер**, и Solo VPS не требует второго VPS, VM, always-on controller host, Vault, KMS или другого secrets service.

Проект использует SOPS + age только для инфраструктурных/recovery-значений, которые нельзя коммитить в Git в plaintext. Переменные окружения приложений остаются в Coolify.

## Решение

Хранить один production private age key на **рабочей станции оператора**. Сгенерированные public recipient/policy state хранить вне публичного checkout продукта; приватный operator repository может намеренно хранить SOPS ciphertext, когда конкретной функции это необходимо.

Рекомендуемая модель:

```text
Домашняя рабочая станция Windows или Linux
  один приватный age key
  опциональная backup-копия в месте, откуда оператор сможет восстановиться

persistent state рабочей станции
  публичный age recipient
  SOPS policy

Git/private operator repository, если используется намеренно
  зашифрованные *.enc.yaml файлы

один VPS
  по умолчанию без production private age key
  только конкретные runtime credentials, если они реально нужны сервису

Coolify
  runtime secrets приложений
```

Для этого не нужен второй сервер. Также не требуется отдельная SSH identity или отдельный Ansible controller только ради секретов.

## Операционное правило

Схема должна оставаться простой:

1. один раз сгенерировать age key на домашней рабочей станции;
2. при желании сохранить/скопировать private key в восстановимое место;
3. инициализировать persistent public recipient/policy state вне checkout продукта;
4. шифровать инфраструктурные secret files через SOPS, когда они действительно нужны конкретной функции;
5. по умолчанию не копировать production private age key ни в Git, ни на VPS.

Будущая интеграция сервиса может материализовать на VPS один конкретный runtime credential. Такая реализация относится к milestone, которому credential действительно нужен (например, backup storage), а не к общему M13 secret-delivery framework.

## Почему

Так Solo VPS получает полезную часть SOPS + age без enterprise-церемоний:

- утечка Git repository не раскрывает plaintext infrastructure credentials;
- потеря/переустановка VPS не уничтожает единственный decryption key;
- пользователь управляет одним ключом, а не secret-management platform;
- архитектура «один VPS» остаётся одним VPS.

## Последствия

### Плюсы

- очень маленькая операционная поверхность;
- подходят и Windows-, и Linux-рабочие станции;
- не нужен второй сервер или always-on controller;
- не обязателен внешний KMS/Vault account;
- private age material остаётся вне Git.

### Минусы

- если потеряна единственная копия private age key, зашифрованные файлы нельзя расшифровать;
- пользователь должен хранить ключ там, откуда сможет его восстановить;
- нативная установка SOPS/age различается между Windows и Linux.

## Восстановление

Backup-копия рекомендуется, но не требует отдельной сложной процедуры. Secure note/file attachment в password manager, зашифрованный внешний диск или другое контролируемое оператором backup-место достаточно для baseline Solo VPS.

Recovery proof для M13 прост: копия production key должна вывести тот же public recipient и расшифровать disposable SOPS file. Отдельный recovery server не нужен.

## Проверка

M13 завершён, когда:

1. repository policy не содержит private age identity или plaintext secret source;
2. pinned SOPS + age crypto доказана disposable roundtrip;
3. оператор сгенерировал одну production age identity на Windows- или Linux-рабочей станции;
4. public recipient инициализирует persistent workstation SOPS policy/recipient files вне checkout;
5. disposable encrypted file успешно encrypt/decrypt через workstation key;
6. production private age identity отсутствует на VPS.

Доставка конкретных runtime credentials проверяется milestone, который вводит соответствующий credential.

M14 реализует первый такой конкретный путь без изменения one-key model: зашифрованный backup bundle остаётся в persistent workstation state, рабочая станция расшифровывает его только для явного push, а plaintext передаётся на managed VPS через SSH stdin. VPS хранит только `/etc/solo-vps/backup/credentials.json` как `root:root 0600`; production private age key туда не копируется. Этот узкий backup helper не является универсальным secret-distribution service.
