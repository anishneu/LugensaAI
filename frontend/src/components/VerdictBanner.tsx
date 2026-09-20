import { CheckBadgeIcon, ExclamationCircleIcon, QuestionMarkCircleIcon } from "@heroicons/react/24/outline";
import type { ResearchResponse } from "../types";
import { computeVerdict } from "../verdict";
import type { VerdictTone } from "../verdict";

interface VerdictBannerProps {
  response: ResearchResponse;
}

const TONE: Record<VerdictTone, { box: string; badge: string; Icon: typeof CheckBadgeIcon }> = {
  positive: { box: "border-emerald-500/40 bg-emerald-500/[0.08]", badge: "bg-emerald-500/20 text-[var(--supported)]", Icon: CheckBadgeIcon },
  mixed: { box: "border-amber-500/40 bg-amber-500/[0.08]", badge: "bg-amber-500/20 text-[var(--insufficient)]", Icon: ExclamationCircleIcon },
  insufficient: { box: "border-[var(--border)] bg-[var(--bg-alt)]", badge: "bg-[var(--bg)] text-[var(--text-muted)]", Icon: QuestionMarkCircleIcon },
  unknown: { box: "border-[var(--border)] bg-[var(--bg-alt)]", badge: "bg-[var(--bg)] text-[var(--text-muted)]", Icon: QuestionMarkCircleIcon },
};

export function VerdictBanner({ response }: VerdictBannerProps) {
  const verdict = computeVerdict(response);
  const { box, badge, Icon } = TONE[verdict.tone];
  const coveredTopics = new Set(response.claims.filter((c) => c.status === "supported").map((c) => c.claim_type)).size;
  const stats: [string, string][] = [
    [`${coveredTopics}/${response.topics.length}`, "topics supported"],
    [String(response.evidence.length), "sources"],
    [String(response.claims.length), "claims checked"],
  ];

  return (
    <div className={`rounded-2xl border p-5 ${box}`}>
      <span className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-bold tracking-[0.08em] uppercase ${badge}`}>
        <Icon className="h-4 w-4" aria-hidden="true" />
        {verdict.label}
      </span>
      <p className="m-0 mt-3 text-[15px] leading-relaxed font-medium text-[var(--text-h)]" dir="auto">
        {response.recommendation}
      </p>
      <dl className="m-0 mt-4 flex flex-wrap gap-x-6 gap-y-2">
        {stats.map(([value, label]) => (
          <div key={label} className="flex items-baseline gap-1.5">
            <dt className="text-lg font-bold text-[var(--text-h)]">{value}</dt>
            <dd className="m-0 text-xs text-[var(--text-muted)]">{label}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
