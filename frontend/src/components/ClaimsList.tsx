import type { Claim } from "../types";

const STATUS_LABEL: Record<Claim["status"], string> = {
  supported: "Supported",
  contradicted: "Contradicted",
  insufficient_evidence: "Insufficient evidence",
};

interface ClaimsListProps {
  claims: Claim[];
}

export function ClaimsList({ claims }: ClaimsListProps) {
  if (claims.length === 0) {
    return <p className="empty-note">No claims were extracted from the collected evidence.</p>;
  }

  const byTopic = new Map<string, Claim[]>();
  for (const claim of claims) {
    const list = byTopic.get(claim.claim_type) ?? [];
    list.push(claim);
    byTopic.set(claim.claim_type, list);
  }

  return (
    <div className="claims-list">
      {[...byTopic.entries()].map(([topic, topicClaims]) => (
        <div key={topic} className="claims-topic-group">
          <h4>{topic.replace(/_/g, " ")}</h4>
          {topicClaims.map((claim) => (
            <div key={claim.claim_id} className={`claim-card claim-${claim.status}`}>
              <div className="claim-header">
                <span className={`status-badge status-${claim.status}`}>{STATUS_LABEL[claim.status]}</span>
                <span className="evidence-count">
                  {claim.supporting_evidence_ids.length} source
                  {claim.supporting_evidence_ids.length === 1 ? "" : "s"}
                </span>
              </div>
              <p>{claim.text}</p>
              {claim.limitations.length > 0 && (
                <ul className="claim-limitations">
                  {claim.limitations.map((limitation, i) => (
                    <li key={i}>{limitation}</li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
