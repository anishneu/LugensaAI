import { CheckCircleIcon, ExclamationTriangleIcon, QuestionMarkCircleIcon } from "@heroicons/react/24/outline";
import type { Claim } from "../types";

const STATUS: Record<Claim["status"], { label: string; card: string; badge: string; Icon: typeof CheckCircleIcon }> = {
  supported: {
    label: "Supported",
    card: "border-l-[var(--supported)]",
    badge: "bg-emerald-500/15 text-[var(--supported)]",
    Icon: CheckCircleIcon,
  },
  contradicted: {
    label: "Contradicted",
    card: "border-l-[var(--contradicted)]",
    badge: "bg-red-500/15 text-[var(--contradicted)]",
    Icon: ExclamationTriangleIcon,
  },
  insufficient_evidence: {
    label: "Insufficient evidence",
    card: "border-l-[var(--insufficient)]",
    badge: "bg-amber-500/15 text-[var(--insufficient)]",
    Icon: QuestionMarkCircleIcon,
  },
};

interface ClaimsListProps {
  claims: Claim[];
}

export function ClaimsList({ claims }: ClaimsListProps) {
  if (claims.length === 0) {
    return (
      <p className="m-0 rounded-2xl border border-dashed border-[var(--border)] p-6 text-center text-sm text-[var(--text-muted)]">
        No claims were extracted from the collected evidence.
      </p>
    );
  }

  const byTopic = new Map<string, Claim[]>();
  for (const claim of claims) {
    const list = byTopic.get(claim.claim_type) ?? [];
    list.push(claim);
    byTopic.set(claim.claim_type, list);
  }

  return (
    <div className="flex flex-col gap-6">
      {[...byTopic.entries()].map(([topic, topicClaims]) => (
        <section key={topic}>
          <h4 className="m-0 mb-2.5 text-[11px] font-bold tracking-[0.1em] text-[var(--text-muted)] uppercase">{topic.replace(/_/g, " ")}</h4>
          <div className="flex flex-col gap-2.5">
            {topicClaims.map((claim) => {
              const { label, card, badge, Icon } = STATUS[claim.status];
              return (
                <article
                  key={claim.claim_id}
                  className={`rounded-xl border border-l-4 border-[var(--border)] bg-[var(--bg-alt)] p-4 ${card}`}
                >
                  <div className="mb-2 flex items-center justify-between gap-3">
                    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${badge}`}>
                      <Icon className="h-3.5 w-3.5" aria-hidden="true" />
                      {label}
                    </span>
                    <span className="text-[11px] text-[var(--text-muted)]">
                      {claim.supporting_evidence_ids.length} source{claim.supporting_evidence_ids.length === 1 ? "" : "s"}
                    </span>
                  </div>
                  <p className="m-0 text-sm leading-relaxed text-[var(--text)]" dir="auto">
                    {claim.text}
                  </p>
                  {claim.limitations.length > 0 && (
                    <ul className="m-0 mt-2.5 list-disc pl-5 text-xs leading-relaxed text-[var(--insufficient)]">
                      {claim.limitations.map((limitation, j) => (
                        <li key={j}>{limitation}</li>
                      ))}
                    </ul>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}
