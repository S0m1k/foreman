import type { Metadata } from "next";
import { formatM, systemColour } from "@/components/takeoff/model";
import { Mark } from "@/components/ui/Mark";
import { IconBack, IconCheck, IconKit, IconSheets, IconUpload } from "@/components/ui/icons";

export const metadata: Metadata = { title: "Дизайн-система — Foreman" };

const SURFACES = [
  ["--ground", "Рамка: сайдбар и поля вокруг листа"],
  ["--surface", "Лист и карточки"],
  ["--raised", "Ступень внутри листа, холст чертежа"],
  ["--active", "Активный пункт, выбранная строка"],
  ["--border", "Кромка листа и карточек"],
  ["--rule", "Линия строки таблицы"],
  ["--control", "Кромка контрола"],
];
const INKS = [
  ["--text", "Текст"],
  ["--muted", "Вторичный текст"],
  ["--faint", "Плейсхолдеры, тире"],
  ["--positive", "Хорошо"],
  ["--negative", "Ошибка, превышение"],
  ["--warning", "Внимание"],
];
const SYSTEMS = ["П1", "П2", "В1", "В2", "ДВ1", "ПД1"];
// sample rows: a parking plan's supply systems, totals computed from the rows
const ROWS = [
  { system: "П1", section: "600x350", insulated: true, length: 12.0 },
  { system: "П1", section: "400x200", insulated: true, length: 5.0 },
  { system: "В1", section: "600x350", insulated: false, length: 14.0 },
  { system: "В1", section: "400x200", insulated: false, length: 5.0 },
  { system: "ДВ1", section: "800x500", insulated: false, length: 10.0 },
];
const total = ROWS.reduce((sum, r) => sum + r.length, 0);

function Section({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <section className="mb-10">
      <h2>{title}</h2>
      {note && <p className="text-sm muted mt-1 max-w-[70ch]">{note}</p>}
      <div className="mt-4">{children}</div>
    </section>
  );
}

function Swatch({ token, note }: { token: string; note: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="w-10 h-10 rounded-[var(--radius-control)] border border-[var(--border)] flex-none" style={{ background: `var(${token})` }} />
      <span className="min-w-0">
        <span className="code block">{token}</span>
        <span className="text-xs muted">{note}</span>
      </span>
    </div>
  );
}

export default function UiKit() {
  return (
    <div className="max-w-[1100px]">
      <div className="page-head">
        <div>
          <h1>Дизайн-система</h1>
          <p>Токены и компоненты Foreman. Описание и правила — docs/design/DESIGN.md.</p>
        </div>
      </div>

      <Section title="Знак и иконки" note="Знак — условное обозначение вертикального воздуховода на плане. Иконки — один контурный набор, 16px, серые.">
        <div className="flex items-center gap-6">
          <span className="flex items-center gap-2 font-semibold text-[15px]"><Mark /> Foreman</span>
          <span className="flex items-center gap-4 muted">
            <IconSheets /><IconUpload /><IconCheck /><IconKit /><IconBack />
          </span>
        </div>
      </Section>

      <Section title="Поверхности и текст" note="Цвет в хроме отсутствует: он живёт только на данных и на статусе.">
        <div className="grid grid-cols-3 max-[900px]:grid-cols-1 gap-4">
          {[...SURFACES, ...INKS].map(([t, n]) => <Swatch key={t} token={t} note={n} />)}
        </div>
      </Section>

      <Section title="Цвета систем" note="Цвета самих чертежей ОВ: приток, вытяжка, дымоудаление, подпор. Внутри семейства у каждой системы своя светлота. Не ниже 3:1 на белом.">
        <div className="flex flex-wrap gap-5">
          {SYSTEMS.map((s) => (
            <span key={s} className="inline-flex items-center gap-2 font-medium">
              <span className="dot" style={{ background: systemColour(s) }} /> {s}
            </span>
          ))}
        </div>
      </Section>

      <Section title="Типографика" note="IBM Plex Sans, цифры табличные. IBM Plex Mono — только для кодов и идентификаторов.">
        <div className="panel">
          {[
            ["Заголовок экрана · 22/600", <h1 key="h">Корпус 18 — ОВ2, изм. 3</h1>],
            ["Заголовок блока · 16/600", <h2 key="s">Сверка со спецификацией</h2>],
            ["Ведущая цифра · 28/400", <span key="l" className="num text-[28px] leading-9">3 283,1 <span className="text-sm muted">м</span></span>],
            ["Текст · 14/400", <span key="b">Ни одна система не превышает спецификацию.</span>],
            ["Подпись · 12/400", <span key="m" className="text-xs muted">по проекту 169,3 из 457,1 м по спецификации</span>],
            ["Код · Plex Mono 13", <span key="c" className="code">tko_a4799aee1a53</span>],
          ].map(([label, sample], i) => (
            <div key={i} className={`grid grid-cols-[220px_1fr] items-baseline gap-4 px-5 py-3 ${i > 0 ? "border-t border-[var(--rule)]" : ""}`}>
              <span className="text-xs muted">{label}</span>
              {sample}
            </div>
          ))}
        </div>
      </Section>

      <Section title="Кнопки" note="Одна основная на экран, почти чёрная. Высота одна в ряду.">
        <div className="flex flex-wrap items-center gap-3">
          <button className="btn btn-primary">Ведомость XLSX</button>
          <button className="btn btn-secondary">Пересчитать</button>
          <button className="btn btn-text">Повторить</button>
          <button className="btn btn-danger">Удалить проект</button>
          <button className="btn btn-primary" disabled>Посчитать</button>
          <button className="btn btn-primary btn-lg">Посчитать</button>
        </div>
      </Section>

      <Section title="Пилюли" note="Бледный фон и тёмный текст того же оттенка; только в строке или рядом со значением.">
        <div className="flex flex-wrap gap-3">
          <span className="pill pill-positive">сходится</span>
          <span className="pill pill-negative">+1,0 м сверх</span>
          <span className="pill pill-warning">нет в спец.</span>
          <span className="pill pill-neutral">ещё 297,2 м</span>
          <span className="pill pill-info">1:100</span>
        </div>
      </Section>

      <Section title="Поля и сегменты">
        <div className="grid grid-cols-2 max-[900px]:grid-cols-1 gap-6 items-start">
          <label className="field">
            <span>Название</span>
            <input className="input" placeholder="Корпус 18 — вентиляция, изм. 3" />
            <small>Необязательно: по умолчанию — имя файла альбома.</small>
          </label>
          <div className="field">
            <span>Масштаб просмотра</span>
            <div className="segmented" role="group" aria-label="Масштаб просмотра">
              <button aria-pressed="true">100%</button><button aria-pressed="false">200%</button>
              <button aria-pressed="false">400%</button><button aria-pressed="false">800%</button>
            </div>
          </div>
        </div>
      </Section>

      <Section title="Показатели" note="Одна панель, разделённая линиями; подпись над значением, единица — серым.">
        <div className="panel grid grid-cols-4 max-[900px]:grid-cols-2">
          {[["Воздуховоды на планах", "3 283,1", "м", true], ["Систем сверх спецификации", "0", "", false], ["Не разнесено", "175,3", "м", false], ["Решётки и клапаны", "330", "из 430", false]].map(([label, value, unit, lead], i) => (
            <div key={String(label)} className={`px-5 py-4 ${i > 0 ? "border-l border-[var(--border)]" : ""}`}>
              <div className="text-xs muted">{label}</div>
              <div className={`num mt-1 ${lead ? "text-[28px]" : "text-[22px]"} leading-9`}>{value} <span className="text-sm muted">{unit}</span></div>
            </div>
          ))}
        </div>
      </Section>

      <Section title="Таблица" note="Заголовки серые, без заливки и капса; числа вправо; отсутствие — тире, ноль — ноль.">
        <section className="panel">
          <header className="panel-head"><h3>Ведомость воздуховодов</h3><span className="meta">План 1 этажа</span></header>
          <table className="table">
            <thead><tr><th>Система</th><th>Сечение</th><th>Изоляция</th><th className="num">Длина, м</th></tr></thead>
            <tbody>
              {ROWS.map((r, i) => (
                <tr key={i}>
                  <td><span className="inline-flex items-center gap-2 font-medium"><span className="dot" style={{ background: systemColour(r.system) }} />{r.system}</span></td>
                  <td className="tabular-nums">{r.section}</td>
                  <td>{r.insulated ? "да" : <span className="dash">—</span>}</td>
                  <td className="num">{formatM(r.length)}</td>
                </tr>
              ))}
              <tr><td className="font-medium">Итого</td><td /><td /><td className="num font-medium">{formatM(total)}</td></tr>
            </tbody>
          </table>
        </section>
      </Section>

      <Section title="Штамп листа" note="Фирменный элемент редактора: основная надпись листа по ГОСТ 21.101, сокращённая.">
        <div className="stamp w-fit">
          <div><span className="k">Шифр</span><span className="v">1181-18-2024-Р-ОВ2</span></div>
          <div><span className="k">Лист</span><span className="v num">6</span></div>
          <div><span className="k">Масштаб</span><span className="v num">1:100</span></div>
          <div><span className="k">Итого</span><span className="v num">1 700,3 м</span></div>
        </div>
      </Section>

      <Section title="Состояния" note="Пустой блок хранит рамку и одну фразу; загрузка — бруски реального размера; ошибка — внутри блока.">
        <div className="grid grid-cols-2 max-[900px]:grid-cols-1 gap-4">
          <p className="empty">На планах нет подписей решёток и клапанов.</p>
          <div className="panel p-5 flex flex-col gap-3">
            <span className="skeleton h-4 w-48" /><span className="skeleton h-9 w-32" />
          </div>
          <p className="panel p-4 text-sm"><span className="error-line">Не удалось загрузить расчёт. Последние данные — 09:14.</span> <button className="btn btn-text">Повторить</button></p>
          <p className="notice">Спецификация прочитана частично: 3 строки без системы пропущены.</p>
        </div>
      </Section>
    </div>
  );
}
