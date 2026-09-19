import type { Evidence } from "../types";

const languageNames = new Intl.DisplayNames(["en"], { type: "language" });

function languageName(code: string): string {
  try {
    return languageNames.of(code) ?? code;
  } catch {
    return code;
  }
}

/** Says when evidence is not in the source's own words. A machine translation
 * is never shown as if it were the original: it's labeled, and the original
 * passage stays one click away. Foreign text that could not be translated is
 * labeled too, rather than shown as if it were readable. `inline` renders a
 * hover-only badge (no nested interactive element) for cards that are
 * themselves links. */
export function TranslationNote({ item, inline = false }: { item: Evidence; inline?: boolean }) {
  const language = item.metadata.language;
  if (!language || language === "en") return null;

  const name = languageName(language);
  const original = item.metadata.original_text;

  if (!original) {
    return (
      <span className="inline-block rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-[10.5px] text-[var(--insufficient)]">
        🌐 {name} — not translated
      </span>
    );
  }

  const badge = (
    <span
      className="inline-block rounded-full border border-sky-500/40 bg-sky-500/10 px-2 py-0.5 text-[10.5px] text-sky-600 dark:text-sky-300"
      title={inline ? `Original (${name}): ${original}` : undefined}
    >
      🌐 Machine-translated from {name}
    </span>
  );

  if (inline) return badge;

  return (
    <details className="my-1.5 text-xs">
      <summary className="cursor-pointer list-none">{badge} <span className="text-[var(--text-muted)] underline">show original</span></summary>
      <p className="m-0 mt-1.5 rounded-lg border border-[var(--border)] bg-[var(--bg)] p-2 text-[var(--text-muted)]" lang={language}>
        {item.metadata.original_title && <strong className="block text-[var(--text)]">{item.metadata.original_title}</strong>}
        {original}
      </p>
    </details>
  );
}
