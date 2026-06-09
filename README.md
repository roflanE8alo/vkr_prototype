# Прототип модели знаний ВКР

Компактный исследовательский прототип для представления ситуаций пошаговых стратегий в виде баз знаний в стиле концептуальных графов и применения одношаговых правил вывода вида «если-то».

Активный демонстрационный контур содержит три успешных сценария на основе Empire Deluxe:

- `EXP-EMPIRE-CAPTURE-01`
- `EXP-EMPIRE-TRANSPORT-02`
- `EXP-EMPIRE-PRODUCTION-01`

## Запуск тестов

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m unittest discover -s tests -v
```

## Запуск экспериментов

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python scripts/run_experiments.py
```

Скрипт запуска экспериментов записывает машинно-читаемые результаты в `artifacts/experiment_results.json`.

## Документация

- `docs/experiment_report.md` - компактный отчёт по экспериментам.
- `docs/empire_deluxe_experiment_scenarios.md` - описания активных сценариев.
- `docs/validation_test_matrix.md` - текущая матрица трассируемости.
