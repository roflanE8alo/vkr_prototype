# Демонстрационные сценарии Empire Deluxe

Активный демонстрационный контур сокращён до трёх успешных сценариев. Они выбраны как компактная витрина прототипа: захват цели, логистика и производство.

Каждый сценарий проходит полный путь `DSL -> AST -> KnowledgeBase -> семантическая валидация -> вывод`. Прототип не симулирует игру Empire Deluxe; игровые факты уже заданы в DSL-файле.

## Сценарии

| ID сценария | Семейство | Файл сценария | Назначение | Ожидаемый результат |
|---|---|---|---|---|
| EXP-EMPIRE-CAPTURE-01 | захват | `tests/fixtures/empire_deluxe/capture_neutral_city_success.kb` | Показать тактическую рекомендацию захвата нейтрального города Army. | `CaptureRecommendation` |
| EXP-EMPIRE-TRANSPORT-02 | транспорт | `tests/fixtures/empire_deluxe/transport_load_success.kb` | Показать логистическую рекомендацию загрузки Army в Transport при свободной вместимости. | `LoadTransportRecommendation` |
| EXP-EMPIRE-PRODUCTION-01 | производство | `tests/fixtures/empire_deluxe/landlocked_city_produces_army_only.kb` | Показать производственную рекомендацию для landlocked city и отсутствие морского юнита в результирующем графе. | `ProductionRecommendation` для Army |

## Общие параметры

- исходный граф: `current_situation`;
- режим вывода: одношаговый;
- объяснения: включены;
- подавление дубликатов: не используется в компактном исполняемом контуре;
- команда: `python scripts/run_experiments.py`;
- машинно-читаемый результат: `artifacts/experiment_results.json`.

## Критерии прохождения

- файл сценария загружается без блокирующих ошибок;
- KnowledgeBase проходит семантическую валидацию;
- срабатывает ожидаемое правило;
- создаются `Hypothesis`, `DerivationRecord`, `Explanation`;
- повторный запуск воспроизводим;
- `KnowledgeBase.graphs` не мутируется;
- сгенерированный результирующий граф находится в `InferenceSession.generated_graphs`.
