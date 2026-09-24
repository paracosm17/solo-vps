Глава 11 — Disaster recovery / restore test

[ПОКА ЧТО НЕ СДЕЛАНА, ПОСКОЛЬКО НЕ ВЫПОЛНЕНА ГЛАВА 10. ТАК КАК НЕТ ОТДЕЛЬНОГО VPS ДЛЯ БЭКАПОВ.
ПУНКТ С БЕКАПАМИ ПОКА ПРОПУСКАЕМ.]

Отдельно проверим восстановление.

Например:

clean restore directory;
восстановление Grafana/Loki/Prometheus state;
восстановление application data;
восстановление secrets;
проверка permissions;
процедура восстановления VPS «с нуля»;
RPO/RTO;
disaster-recovery runbook.

После этой главы можно будет честно сказать: backup проверен восстановлением, а не просто «restic пишет какие-то snapshots».