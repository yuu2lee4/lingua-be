"use client";

import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { JobProgress } from "@/types/job";
import { getLanguageName } from "@/lib/utils/languages";

const phaseLabels: Record<string, string> = {
  pending: "Pending",
  translating: "Translating",
  quality_review: "Quality Review",
  retrying: "Retrying",
  consistency_review: "Consistency Review",
  completed: "Completed",
  failed: "Failed",
};

interface ProgressTrackerProps {
  progress: JobProgress;
  status: string;
}

export function ProgressTracker({ progress, status }: ProgressTrackerProps) {
  const phases = [
    "translating",
    "quality_review",
    "retrying",
    "consistency_review",
    "completed",
  ];
  const currentIdx = phases.indexOf(progress.current_phase);

  const translationPercent =
    progress.total_languages > 0
      ? Math.round(
          (progress.completed_languages / progress.total_languages) * 100
        )
      : 0;

  const consistencyPercent =
    progress.total_consistency_pairs > 0
      ? Math.round(
          (progress.completed_consistency_pairs /
            progress.total_consistency_pairs) *
            100
        )
      : 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 flex-wrap">
        {phases.map((phase, idx) => (
          <div key={phase} className="flex items-center gap-1">
            <Badge
              variant={
                idx < currentIdx
                  ? "default"
                  : idx === currentIdx && status !== "completed" && status !== "failed"
                    ? "secondary"
                    : phase === "completed" && status === "completed"
                      ? "default"
                      : "outline"
              }
              className="text-xs"
            >
              {phaseLabels[phase] || phase}
            </Badge>
            {idx < phases.length - 1 && (
              <span className="text-muted-foreground">→</span>
            )}
          </div>
        ))}
      </div>

      <div className="space-y-3">
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span>
              Translation Progress
              {progress.current_language && (
                <span className="text-muted-foreground ml-2">
                  ({getLanguageName(progress.current_language)})
                </span>
              )}
            </span>
            <span>
              {progress.completed_languages}/{progress.total_languages}
            </span>
          </div>
          <Progress value={translationPercent} />
        </div>

        {progress.total_consistency_pairs > 0 && (
          <div>
            <div className="flex justify-between text-sm mb-1">
              <span>
                Consistency Review
                {progress.current_consistency_pair && (
                  <span className="text-muted-foreground ml-2">
                    ({progress.current_consistency_pair})
                  </span>
                )}
              </span>
              <span>
                {progress.completed_consistency_pairs}/
                {progress.total_consistency_pairs}
              </span>
            </div>
            <Progress value={consistencyPercent} />
          </div>
        )}

        {progress.retry_count > 0 && (
          <p className="text-sm text-muted-foreground">
            Retries: {progress.retry_count}
          </p>
        )}
      </div>
    </div>
  );
}
