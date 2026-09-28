"use client";

import { cn } from "@/lib/utils";

interface QualityScoreProps {
  score: number | null;
  size?: "sm" | "md" | "lg";
}

function getScoreColor(score: number): string {
  if (score >= 95) return "text-green-600 dark:text-green-400";
  if (score >= 80) return "text-yellow-600 dark:text-yellow-400";
  return "text-red-600 dark:text-red-400";
}

function getScoreBg(score: number): string {
  if (score >= 95) return "bg-green-100 dark:bg-green-900/30";
  if (score >= 80) return "bg-yellow-100 dark:bg-yellow-900/30";
  return "bg-red-100 dark:bg-red-900/30";
}

const sizeClasses = {
  sm: "h-8 w-8 text-xs",
  md: "h-12 w-12 text-sm",
  lg: "h-16 w-16 text-lg",
};

export function QualityScore({ score, size = "sm" }: QualityScoreProps) {
  if (score === null || score === undefined) {
    return (
      <div
        className={cn(
          "flex items-center justify-center rounded-full bg-muted text-muted-foreground font-medium",
          sizeClasses[size]
        )}
      >
        —
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-full font-bold",
        getScoreBg(score),
        getScoreColor(score),
        sizeClasses[size]
      )}
    >
      {score}
    </div>
  );
}
