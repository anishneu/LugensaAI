import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  GlobeAltIcon,
  MapPinIcon,
  QuestionMarkCircleIcon,
  StarIcon,
} from "@heroicons/react/24/solid";

/**
 * The workspace as it is laid out, drawn with placeholder bars: the map and the question box on the left, the answer in
 * the middle under its tabs, the live feed on the right. It states nothing about any real place: an earlier version of
 * the landing page showed an invented sample answer with real-looking sources, which is exactly what this project exists
 * not to do. So there are no figures here either, only the app's own vocabulary (the tab names, the three claim statuses,
 * the kinds of source) around bars that stand for text.
 */

function Bar({ w, className = "" }: { w: string; className?: string }) {
  return <span className={`block h-2 rounded-full bg-white/[0.12] ${className}`} style={{ width: w }} />;
}

const CLAIMS = [
  { status: "Supported", Icon: CheckCircleIcon, tone: "text-emerald-300 bg-emerald-400/10 ring-emerald-400/25", source: "Google Maps", widths: ["92%", "64%"] },
  { status: "Supported", Icon: CheckCircleIcon, tone: "text-emerald-300 bg-emerald-400/10 ring-emerald-400/25", source: "Reddit", widths: ["84%", "48%"] },
  { status: "Contradicted", Icon: ExclamationTriangleIcon, tone: "text-rose-300 bg-rose-400/10 ring-rose-400/25", source: "Local forum", widths: ["78%", "56%"] },
  { status: "Insufficient evidence", Icon: QuestionMarkCircleIcon, tone: "text-amber-300 bg-amber-400/10 ring-amber-400/25", source: "News", widths: ["70%", "36%"] },
];

/** A stylised street map: lines and blocks, with the pin in the middle. Decoration, not a place. */
function MiniMap() {
  return (
    <div className="relative h-36 overflow-hidden rounded-xl border border-white/10 bg-[#141227]">
      <svg viewBox="0 0 200 140" className="absolute inset-0 h-full w-full" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <g fill="rgba(255,255,255,0.04)">
          <rect x="6" y="8" width="52" height="34" rx="3" />
          <rect x="70" y="8" width="44" height="34" rx="3" />
          <rect x="126" y="8" width="68" height="34" rx="3" />
          <rect x="6" y="54" width="52" height="30" rx="3" />
          <rect x="126" y="54" width="68" height="30" rx="3" />
          <rect x="6" y="96" width="52" height="38" rx="3" />
          <rect x="70" y="96" width="44" height="38" rx="3" />
          <rect x="126" y="96" width="68" height="38" rx="3" />
        </g>
        <g stroke="rgba(255,255,255,0.14)" strokeWidth="5" strokeLinecap="round" fill="none">
          <path d="M0 48 H200" />
          <path d="M0 90 H200" />
          <path d="M64 0 V140" />
          <path d="M120 0 V140" />
        </g>
        <path d="M0 122 C50 100 110 118 200 70" stroke="rgba(139,92,246,0.35)" strokeWidth="3" strokeLinecap="round" fill="none" />
      </svg>
      <span className="absolute top-1/2 left-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-violet-500 shadow-[0_0_0_8px_rgba(139,92,246,0.25)]" />
    </div>
  );
}

/** The two browser-style tabs above the answer, drawn with the same shape as the app's (see `.browser-tab` in index.css). */
function PreviewBrowserTabs() {
  return (
    <div className="overflow-hidden rounded-xl border border-white/10 bg-[#080714]">
      <div className="flex items-end gap-0.5 pt-1.5 pl-2.5 text-[10.5px] font-medium">
        <span className="relative -mb-px flex items-center gap-1.5 rounded-t-lg bg-[#171529] px-3 py-1.5 text-white/85">
          <StarIcon className="h-3 w-3 text-white/60" aria-hidden="true" />
          Google Maps
          <span className="flex items-center gap-0.5 text-white/45">
            <StarIcon className="h-2.5 w-2.5 text-amber-400" aria-hidden="true" />
            <Bar w="18px" className="h-1.5" />
          </span>
        </span>
        <span className="flex items-center gap-1.5 rounded-t-lg bg-white/[0.05] px-3 py-1.5 text-white/45">
          <GlobeAltIcon className="h-3 w-3" aria-hidden="true" />
          Around this pin
        </span>
      </div>
      <div className="flex gap-3 border-t border-white/10 bg-[#171529] p-3">
        <div className="flex flex-1 flex-col gap-2">
          <div className="flex items-center gap-2">
            <span className="flex gap-px">
              {[0, 1, 2, 3, 4].map((n) => (
                <StarIcon key={n} className="h-3 w-3 text-amber-400/70" aria-hidden="true" />
              ))}
            </span>
            <Bar w="46px" className="h-1.5" />
            <span className="rounded-full bg-white/[0.07] px-2 py-0.5 text-[9px] text-emerald-300/90">Open now ▾</span>
          </div>
          <Bar w="88%" />
          <Bar w="58%" />
        </div>
        {/* the reviews list scrolls, with its bar showing */}
        <div className="relative flex w-[42%] flex-col gap-1.5 pr-2.5">
          {[0, 1].map((n) => (
            <div key={n} className="flex flex-col gap-1.5 rounded-lg border border-white/10 bg-white/[0.03] p-2">
              <Bar w="40%" className="h-1.5" />
              <Bar w="92%" className="h-1.5" />
            </div>
          ))}
          <span className="absolute top-0 right-0 h-full w-1 rounded-full bg-white/[0.06]" aria-hidden="true">
            <span className="block h-1/2 w-full rounded-full bg-white/30" />
          </span>
        </div>
      </div>
    </div>
  );
}

export function AnswerPreview() {
  return (
    <figure className="m-0 mx-auto w-full max-w-5xl">
      <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#0d0b1a] shadow-2xl shadow-violet-950/50">
        {/* the app's top bar: title and place on the left, change-location on the right */}
        <div className="flex items-center justify-between gap-3 border-b border-white/10 bg-white/[0.03] px-4 py-2.5">
          <div className="flex min-w-0 items-center gap-3">
            <span className="flex flex-shrink-0 gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
              <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
              <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
            </span>
            <span className="text-xs font-bold text-white/80">
              Lugensa<span className="text-violet-300">AI</span>
            </span>
            <span className="flex min-w-0 items-center gap-1.5 rounded-md bg-white/[0.06] px-2.5 py-1 text-[11px] text-white/50">
              <MapPinIcon className="h-3 w-3 flex-shrink-0" aria-hidden="true" /> <span className="truncate">A place</span>
            </span>
          </div>
          <span className="flex-shrink-0 rounded-full border border-white/15 px-3 py-1 text-[10.5px] text-white/55">Change location</span>
        </div>

        {/* Only the top of the workspace is shown, fading out, so the preview is a glimpse and not a full page of it. */}
        <div className="relative max-h-[420px] overflow-hidden md:max-h-[400px]">
        <div className="grid gap-px bg-white/10 md:grid-cols-[0.8fr_1.6fr_0.8fr]">
          {/* the zoomed-in map, and where you ask */}
          <div className="hidden flex-col gap-4 bg-[#0d0b1a] p-4 md:flex">
            <MiniMap />
            <div className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
              <span className="text-[11px] font-semibold text-white/70">Ask the agent</span>
              <Bar w="85%" />
              <Bar w="55%" />
              <span className="mt-1 self-end rounded-full bg-violet-500/70 px-3 py-1 text-[10px] font-semibold text-white">Ask →</span>
            </div>
          </div>

          {/* the answer */}
          <div className="flex flex-col gap-3.5 bg-[#0d0b1a] p-4 md:p-5">
            <PreviewBrowserTabs />

            {/* the answer's own tabs are underlined */}
            <div className="flex gap-5 border-b border-white/10 text-[11px] font-medium text-white/45">
              {["Overview", "Community", "Claims", "Evidence"].map((tab, i) => (
                <span key={tab} className={`-mb-px border-b-2 px-0.5 pb-2 ${i === 0 ? "border-violet-400 text-violet-300" : "border-transparent"}`}>
                  {tab}
                </span>
              ))}
            </div>

            <div className="rounded-xl border border-emerald-400/25 bg-emerald-400/[0.07] p-4">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-400/15 px-2.5 py-0.5 text-[10px] font-bold tracking-wide text-emerald-300 uppercase">
                <CheckCircleIcon className="h-3 w-3" aria-hidden="true" /> Generally supportive evidence
              </span>
              <div className="mt-3 flex flex-col gap-2">
                <Bar w="96%" className="h-2.5 bg-white/25" />
                <Bar w="72%" className="h-2.5 bg-white/25" />
              </div>
            </div>

            <div className="flex flex-col gap-2">
              {CLAIMS.map((claim, i) => (
                <div key={i} className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ring-1 ${claim.tone}`}>
                      <claim.Icon className="h-3 w-3" aria-hidden="true" />
                      {claim.status}
                    </span>
                    <span className="rounded-md bg-white/[0.07] px-2 py-0.5 text-[10px] text-white/55">{claim.source}</span>
                  </div>
                  <Bar w={claim.widths[0]} />
                  <Bar w={claim.widths[1]} />
                </div>
              ))}
            </div>
          </div>

          {/* live feed */}
          <div className="hidden flex-col gap-3 bg-[#0d0b1a] p-4 md:flex">
            <span className="text-[11px] font-semibold text-white/70">Live feed</span>
            <div className="flex gap-1 rounded-full border border-white/10 bg-white/[0.03] p-1 text-[10px] font-medium text-white/50">
              <span className="flex-1 rounded-full bg-violet-500 py-1 text-center text-white">News</span>
              <span className="flex-1 py-1 text-center">Community</span>
            </div>
            {[0, 1, 2, 3].map((n) => (
              <div key={n} className="flex gap-2.5 rounded-xl border border-white/10 bg-white/[0.03] p-2.5">
                <span className="h-10 w-10 flex-shrink-0 rounded-lg bg-white/[0.09]" />
                <div className="flex flex-1 flex-col gap-1.5 pt-0.5">
                  <Bar w="40%" className="h-1.5" />
                  <Bar w="94%" />
                  <Bar w="70%" />
                </div>
              </div>
            ))}
          </div>
        </div>
        <div className="pointer-events-none absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-[#0d0b1a] to-transparent" aria-hidden="true" />
        </div>
      </div>
      <figcaption className="mt-4 text-center text-xs text-white/40">
        The workspace, drawn with placeholders. Ask about a real place to see it filled in, every bar replaced by a sourced sentence.
      </figcaption>
    </figure>
  );
}
