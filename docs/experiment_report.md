# Отчёт по демонстрационной апробации прототипа

## 1. Цель

Цель демонстрационного набора - кратко показать работу прототипа на трёх успешных сценариях Basic Game Empire Deluxe: тактическое действие, логистика и производство.

Прототип не является игровым движком. Empire Deluxe используется как источник формализованных ситуаций для проверки вывода по концептуальным графам.

## 2. Проверяемый конвейер

1. DSL-файл сценария.
2. Лексер/парсер.
3. AST.
4. Трансляция в `KnowledgeBase`.
5. Семантическая валидация.
6. `GraphMatcher`.
7. `RuleApplier`.
8. `InferenceEngine`.
9. `Hypothesis`, `DerivationRecord`, `Explanation`.
10. Локальные для сеанса `generated_graphs`.

## 3. Сценарии

| ID сценария | Семейство | Файл сценария | Ожидаемый результат | Статус |
|---|---|---|---|---|
| EXP-EMPIRE-CAPTURE-01 | захват | `tests/fixtures/empire_deluxe/capture_neutral_city_success.kb` | `CaptureRecommendation` | пройден |
| EXP-EMPIRE-TRANSPORT-02 | транспорт | `tests/fixtures/empire_deluxe/transport_load_success.kb` | `LoadTransportRecommendation` | пройден |
| EXP-EMPIRE-PRODUCTION-01 | производство | `tests/fixtures/empire_deluxe/landlocked_city_produces_army_only.kb` | `ProductionRecommendation` для Army | пройден |

## 4. Методика запуска

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python scripts/run_experiments.py
python -m unittest discover -s tests -v
```

Скрипт запуска экспериментов сохраняет машинно-читаемый результат в `artifacts/experiment_results.json`.

## 5. Результаты

| ID сценария | Ожидаемая рекомендация | Фактическая рекомендация | Сработавшие правила | Hypothesis | DerivationRecord | Explanation | Статус |
|---|---|---|---|---|---|---|---|
| EXP-EMPIRE-CAPTURE-01 | `CaptureRecommendation` | `CaptureRecommendation` | `CaptureNeutralCityRule` | да | да | да | пройден |
| EXP-EMPIRE-TRANSPORT-02 | `LoadTransportRecommendation` | `LoadTransportRecommendation` | `LoadTransportRule` | да | да | да | пройден |
| EXP-EMPIRE-PRODUCTION-01 | `ProductionRecommendation` | `ProductionRecommendation` | `LandlockedCityProduceArmyRule` | да | да | да | пройден |

## 6. Метрики

| Метрика | Значение |
|---|---:|
| всего демонстрационных сценариев | 3 |
| исполняемых сценариев | 3 |
| успешно пройдено | 3 |
| не пройдено | 0 |
| отложено в активном контуре | 0 |
| доля успешных сценариев | 100% |
| сценариев с Hypothesis | 3 |
| сценариев с DerivationRecord | 3 |
| сценариев с Explanation | 3 |
| воспроизводимых сценариев | 3 |
| сценариев с неизменённым `KnowledgeBase.graphs` | 3 |
| сценариев с локальными для сеанса сгенерированными графами | 3 |
| неожиданных предупреждений | 0 |
| неожиданных ошибок | 0 |

## 7. Вывод

Три сценария достаточны для краткого представления прототипа: они показывают полный DSL-конвейер, успешное графовое сопоставление, применение правила вида «если-то», построение гипотезы, трассировки и объяснения, а также отсутствие мутации исходной `KnowledgeBase`.
