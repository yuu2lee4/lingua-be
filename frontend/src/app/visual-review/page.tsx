"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { ReviewForm } from "@/components/visual-review/review-form";
import { IssueList } from "@/components/visual-review/issue-list";
import { ScoreRadar } from "@/components/visual-review/score-radar";
import { QualityScore } from "@/components/translation/quality-score";
import type { VisualReviewResponse } from "@/types/visual-review";
import { getLanguageName } from "@/lib/utils/languages";

export default function VisualReviewPage() {
  const [result, setResult] = useState<VisualReviewResponse | null>(null);

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">Visual Review</h1>
      <p className="text-muted-foreground">
        Compare translated pages visually against the reference language to catch
        layout and rendering issues.
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Review Configuration</CardTitle>
        </CardHeader>
        <CardContent>
          <ReviewForm onResult={setResult} />
        </CardContent>
      </Card>

      {result && (
        <>
          <Separator />

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Total Languages
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold">{result.total_languages}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Passed
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                  {result.passed_count}
                </p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Failed
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                  {result.failed_count}
                </p>
              </CardContent>
            </Card>
          </div>

          {result.sandbox_error && (
            <Card className="border-destructive">
              <CardHeader>
                <CardTitle className="text-base text-destructive">
                  Sandbox Error
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm">{result.sandbox_error}</p>
              </CardContent>
            </Card>
          )}

          <div className="space-y-4">
            {result.reviews.map((review) => (
              <Card key={review.lang_code}>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <CardTitle className="text-base">
                        {review.lang_name || getLanguageName(review.lang_code)}
                      </CardTitle>
                      <Badge variant="outline" className="text-xs">
                        {review.lang_code}
                      </Badge>
                      <Badge
                        variant={review.passed ? "default" : "destructive"}
                      >
                        {review.passed ? "Passed" : "Failed"}
                      </Badge>
                    </div>
                    <QualityScore score={review.overall_score} size="md" />
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  <ScoreRadar review={review} />

                  {review.feedback && (
                    <div>
                      <p className="text-sm font-medium mb-1">Feedback</p>
                      <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                        {review.feedback}
                      </p>
                    </div>
                  )}

                  {review.issues.length > 0 && (
                    <div>
                      <p className="text-sm font-medium mb-2">
                        Issues ({review.issues.length})
                      </p>
                      <IssueList issues={review.issues} />
                    </div>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
