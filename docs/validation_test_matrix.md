# Матрица валидационных тестов

Текущая матрица описывает компактный демонстрационный прототип после сокращения активного набора тестов с 94 до 12.

## Тесты демонстрационного конвейера

| Сценарий / требование | Имя теста | Статус | Комментарий |
|---|---|---|---|
| Пользовательский раздел `hypotheses` находится вне компактного DSL | `DemoPipelineTests.test_compact_dsl_rejects_user_hypotheses_section` | реализовано | Сгенерированные гипотезы являются только результатами вывода во время выполнения. |
| Файл сценария захвата транслируется в `KnowledgeBase` | `DemoPipelineTests.test_capture_fixture_translates_to_knowledge_base` | реализовано | Проверяет типы, отношения, граф и правило после трансляции. |
| Демонстрационные файлы сценариев проходят проверку готовности к выводу | `DemoPipelineTests.test_semantic_report_accepts_all_demo_fixtures` | реализовано | Используется единый компактный валидатор в `semantic.py`. |
| Сценарий захвата создаёт рекомендацию | `DemoPipelineTests.test_capture_scenario_creates_capture_recommendation` | реализовано | `CaptureNeutralCityRule` создаёт `CaptureRecommendation`. |
| Сценарий транспорта создаёт рекомендацию | `DemoPipelineTests.test_transport_scenario_creates_load_recommendation` | реализовано | `LoadTransportRule` создаёт `LoadTransportRecommendation`. |
| Сценарий производства рекомендует только Army | `DemoPipelineTests.test_production_scenario_creates_army_production_only` | реализовано | Результирующий граф содержит `Army`, но не `Transport`. |
| Вывод детерминирован | `DemoPipelineTests.test_inference_results_are_deterministic` | реализовано | Повторные запуски дают те же сработавшие правила и типы гипотез. |
| Сгенерированные графы локальны для сеанса | `DemoPipelineTests.test_generated_graphs_are_session_local` | реализовано | `KnowledgeBase.graphs` остаётся неизменным; результирующий граф находится в `InferenceSession.generated_graphs`. |
| Создаётся объяснение | `DemoPipelineTests.test_explanation_contains_rule_source_and_hypothesis` | реализовано | Объяснение ссылается на правило, исходный граф и целевую гипотезу. |
| Отсутствующий исходный граф приводит к ошибке запуска | `DemoPipelineTests.test_missing_source_graph_fails_inference_startup` | реализовано | Компактный вывод требует явный `source_graph_id` и проверяет его существование. |
| Отсутствие активных правил приводит к ошибке запуска | `DemoPipelineTests.test_disabled_rules_fail_inference_startup` | реализовано | Покрывает `INFERENCE_READY_NO_ACTIVE_RULES`. |
| Несоответствие сигнатуры отношения фиксируется валидатором | `DemoPipelineTests.test_semantic_validator_reports_relation_type_mismatch` | реализовано | Минимальный семантический валидатор по-прежнему обнаруживает несогласованность графа и сигнатуры. |

## Активные сценарии Empire Deluxe

| ID сценария | Требование | Файл сценария | Тестовая функция | Статус | Комментарий |
|---|---|---|---|---|---|
| EXP-EMPIRE-CAPTURE-01 | Army рядом с нейтральным городом создаёт рекомендацию захвата | `tests/fixtures/empire_deluxe/capture_neutral_city_success.kb` | `DemoPipelineTests.test_capture_scenario_creates_capture_recommendation` | реализовано | Проходит в тестах и скрипте запуска экспериментов. |
| EXP-EMPIRE-TRANSPORT-02 | Army рядом с Transport со свободной вместимостью создаёт рекомендацию загрузки | `tests/fixtures/empire_deluxe/transport_load_success.kb` | `DemoPipelineTests.test_transport_scenario_creates_load_recommendation` | реализовано | Проходит в тестах и скрипте запуска экспериментов. |
| EXP-EMPIRE-PRODUCTION-01 | Landlocked city производит только Army | `tests/fixtures/empire_deluxe/landlocked_city_produces_army_only.kb` | `DemoPipelineTests.test_production_scenario_creates_army_production_only` | реализовано | Проходит в тестах и скрипте запуска экспериментов. |
