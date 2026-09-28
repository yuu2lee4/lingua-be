"use client";

import type { VisualLanguageReview } from "@/types/visual-review";

interface ScoreRadarProps {
  review: VisualLanguageReview;
}

export function ScoreRadar({ review }: ScoreRadarProps) {
  const scores = [
    { label: "Layout", value: review.layout_score },
    { label: "Text Rendering", value: review.text_rendering_score },
    { label: "Completeness", value: review.translation_completeness_score },
    { label: "Accuracy", value: review.expression_accuracy_score },
  ];

  return (
    <div className="grid grid-cols-2 gap-3">
      {scores.map((score) => (
        <div
          key={score.label}
          className="flex flex-col items-center gap-1 rounded-md border p-3"
        >
          <div
            className={`text-2xl font-bold ${
              score.value >= 90
                ? "text-green-600 dark:text-green-400"
                : score.value >= 70
                  ? "text-yellow-600 dark:text-yellow-400"
                  : "text-red-600 dark:text-red-400"
            }`}
          >
            {score.value}
          </div>
          <span className="text-xs text-muted-foreground text-center">
            {score.label}
          </span>
        </div>
      ))}
    </div>
  );
}
