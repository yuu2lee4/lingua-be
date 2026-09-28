"use client";

import { Badge } from "@/components/ui/badge";
import type { VisualIssue } from "@/types/visual-review";

const severityColors: Record<string, "destructive" | "default" | "secondary"> = {
  critical: "destructive",
  major: "default",
  minor: "secondary",
};

interface IssueListProps {
  issues: VisualIssue[];
}

export function IssueList({ issues }: IssueListProps) {
  if (issues.length === 0) {
    return (
      <p className="text-sm text-muted-foreground py-2">No issues found.</p>
    );
  }

  return (
    <div className="space-y-3">
      {issues.map((issue, i) => (
        <div key={i} className="rounded-md border p-3 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={severityColors[issue.severity] || "outline"} className="text-xs capitalize">
              {issue.severity}
            </Badge>
            <Badge variant="outline" className="text-xs">
              {issue.issue_type}
            </Badge>
            {issue.location && (
              <span className="text-xs text-muted-foreground">
                @ {issue.location}
              </span>
            )}
          </div>
          <p className="text-sm">{issue.description}</p>
          {issue.suggestion && (
            <p className="text-sm text-muted-foreground">
              Suggestion: {issue.suggestion}
            </p>
          )}
        </div>
      ))}
    </div>
  );
}
