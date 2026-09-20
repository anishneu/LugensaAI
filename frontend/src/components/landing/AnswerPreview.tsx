import { CheckCircleIcon, ExclamationTriangleIcon, MapPinIcon, QuestionMarkCircleIcon } from "@heroicons/react/24/solid";

/**
 * The shape of an answer, drawn with placeholder bars. It states nothing about any real place: an earlier version of
 * the landing page showed an invented sample answer with real-looking sources, which is exactly what this project
 * exists not to do. The labels here (the three claim statuses, the kinds of source) are the app's own vocabulary.
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

export function AnswerPreview() {
  return (
    <figure className="m-0 mx-auto w-full max-w-5xl">
      <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#0d0b1a] shadow-[0_40px_120px_-30px_rgba(124,58,237,0.55)]">
        {/* window chrome */}
        <div className="flex items-center gap-2 border-b border-white/10 bg-white/[0.03] px-4 py-3">
          <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
          <span className="h-2.5 w-2.5 rounded-full bg-white/20" />
          <span className="ml-3 flex items-center gap-1.5 rounded-md bg-white/[0.06] px-3 py-1 text-[11px] text-white/50">
            <MapPinIcon className="h-3 w-3" aria-hidden="true" /> A place, a question
          </span>
        </div>

        <div className="grid gap-px bg-white/10 md:grid-cols-[0.8fr_1.5fr_0.85fr]">
          {/* map + ask */}
          <div className="hidden flex-col gap-4 bg-[#0d0b1a] p-4 md:flex">
            <div className="relative h-32 overflow-hidden rounded-xl border border-white/10 bg-[radial-gradient(circle_at_30%_30%,rgba(139,92,246,0.35),transparent_60%),linear-gradient(135deg,#1a1730,#0f0d1f)]">
              <div className="absolute inset-0 opacity-40 [background-image:linear-gradient(rgba(255,255,255,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.08)_1px,transparent_1px)] [background-size:22px_22px]" />
              <span className="absolute top-1/2 left-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-violet-500 shadow-[0_0_0_8px_rgba(139,92,246,0.25)]" />
            </div>
            <div className="flex flex-col gap-2 rounded-xl border border-white/10 bg-white/[0.03] p-3">
              <span className="text-[11px] font-semibold text-white/70">Ask the agent</span>
              <Bar w="85%" />
              <Bar w="55%" />
              <span className="mt-1 self-end rounded-full bg-violet-500/70 px-3 py-1 text-[10px] font-semibold text-white">Ask →</span>
            </div>
          </div>

          {/* the answer */}
          <div className="flex flex-col gap-3.5 bg-[#0d0b1a] p-4 md:p-5">
            <div className="flex gap-1 rounded-full border border-white/10 bg-white/[0.03] p-1 text-[10.5px] font-medium text-white/50">
              {["Overview", "Community", "Claims", "Evidence"].map((tab, i) => (
                <span key={tab} className={`rounded-full px-3 py-1 ${i === 0 ? "bg-violet-500 text-white" : ""}`}>
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
              <div className="mt-3 flex gap-5 text-[11px] text-white/50">
                <span>
                  <strong className="text-white/85">3/4</strong> topics supported
                </span>
                <span>
                  <strong className="text-white/85">12</strong> sources
                </span>
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
            {[0, 1, 2].map((n) => (
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
      </div>
      <figcaption className="mt-4 text-center text-xs text-white/40">
        The shape of an answer. Ask about a real place to see one, with every bar replaced by a sourced sentence.
      </figcaption>
    </figure>
  );
}
