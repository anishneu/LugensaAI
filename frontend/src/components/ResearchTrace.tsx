import { useState } from "react";
import type { ResearchTraceStep } from "../types";

interface ResearchTraceProps {
  trace: ResearchTraceStep[];
}

export function ResearchTrace({ trace }: ResearchTraceProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="research-trace">
      <button type="button" className="trace-toggle" onClick={() => setExpanded((v) => !v)}>
        {expanded ? "Hide" : "Show"} research trace ({trace.length} steps)
      </button>
      {expanded && (
        <ol className="trace-steps">
          {trace.map((step, i) => (
            <li key={i}>
              <span className="trace-stage">{step.stage.replace(/_/g, " ")}</span>
              <span className="trace-description">{step.description}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
