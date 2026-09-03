# Foreman — AI Construction Drawing Checker (MVP)

Загрузите PDF-чертёж и PDF-спецификацию — система извлечёт объекты, сопоставит
их и покажет расхождения **с доказательствами** (страница + фрагмент документа
для каждой стороны).

Типы находок: `PARAMETER_MISMATCH`, `QUANTITY_MISMATCH`,
`MISSING_IN_SPECIFICATION`, `MISSING_ON_DRAWING`, `IDENTIFICATION_MISMATCH`.

## Архитектура

```
Next.js (apps/web)
   │ REST
FastAPI (apps/api) ──► Job queue (inline thread | Celery+Redis)
   │                        │
PostgreSQL / SQLite     AI Pipeline:
MinIO / local files       PDF parse (PyMuPDF) → render → OCR (adapter)
                          → entity extraction (rules + tables + VLM*)
                          → grounding (anti-hallucination)
                          → matching (exact → normalized → semantic)
                          → deterministic comparison
                          → verification (VLM* | rules) → findings + evidence
```

\* VLM опциональна: любой OpenAI-совместимый endpoint (vLLM / Ollama /
LM Studio). Рекомендуемая модель — **Qwen3-VL 8B/32B** (лучше Qwen2.5-VL в
документном OCR, включая русский); замена = одна строка конфига
(`VLM_BASE_URL` + `VLM_MODEL`). Без VLM работает детерминированный пайплайн.

Ключевой принцип: **LLM интерпретирует, код решает.** `15000 != 12000`
сравнивает backend; всё, что VLM «увидела», проходит grounding — значение,
которого нет в тексте страницы, отбрасывается. Finding без evidence не
существует по построению.

## Запуск (dev, без Docker)

```bash
python -m venv .venv && .venv/Scripts/pip install -e ".[dev]"
.venv/Scripts/uvicorn dc_api.main:app --port 8000     # API (SQLite + локальные файлы)
cd apps/web && npm install && npm run dev              # UI на :3000
```

## Запуск (Docker Compose: Postgres + Redis + MinIO + Celery)

```bash
cp .env.example .env
docker compose up --build
```

## Тесты и бенчмарк

```bash
.venv/Scripts/python -m pytest                             # 70 тестов, включая e2e по HTTP
.venv/Scripts/python tests/benchmark/run_benchmark.py --projects 20
# реальные PDF: положите drawing.pdf + specification.pdf + ground_truth.json
# в tests/benchmark/data/<проект>/ и запустите с --data-dir tests/benchmark/data
```

Текущий результат на синтетическом корпусе (20 проектов, 120 расхождений):
precision 1.0, recall 1.0. Синтетика дружелюбна — реальные сканы будут хуже;
харнес готов принимать реальные проекты с ground truth.

## Настройки (.env)

См. [.env.example](.env.example): БД, storage (local/S3), очередь
(inline/celery), VLM endpoint, OCR (`auto|paddle|tesseract|none` — PaddleOCR
ставится extra-зависимостью `.[ocr-paddle]`).

## Структура

```
apps/api        FastAPI: роуты, БД, storage, пайплайн (15 стадий с реальными статусами)
apps/worker     Celery worker
apps/web        Next.js 15 + Tailwind 4, 4 экрана (dashboard / upload / results / finding)
packages/       schemas · pdf · ocr · vision · extraction · matching · comparison
prompts/        версионированные промпты (…_v1.txt)
tests/          unit · integration (HTTP e2e) · benchmark
```

## DWG / DXF

Чертёж можно загружать как **DXF** (работает из коробки, ezdxf) или **DWG**
(нужен бесплатный [ODA File Converter](https://www.opendesign.com/guestfiles/oda_file_converter);
путь — `ODA_CONVERTER_PATH`). Пайплайн: DWG → DXF → рендер в PDF (ezdxf +
matplotlib) + текст берётся напрямую из CAD-сущностей (TEXT/MTEXT/атрибуты
блоков) с точными координатами — без OCR. Дальше работает обычный
PDF-пайплайн: evidence, кропы, сравнение.

## Известные ограничения MVP

- BIM/IFC/Revit — вне scope; DWG рендерится по model space (layouts не разворачиваются).
- Уверенности: `extraction`, `matching`, `conflict` считаются раздельно;
  всё с итоговой уверенностью < 0.70 показывается как **Needs review**,
  а не как ошибка (принцип: лучше меньше, но точнее).
- Семантическое сопоставление намеренно консервативно: пары вида
  AHU-36 ↔ AHU-06 не склеиваются; V-03 ↔ V-04 — только как
  identification mismatch с пониженной уверенностью.
