"use client";

import { use } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { XCircle, Clock, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { useJobStatus, useCancelJob } from "@/lib/hooks/use-translation";
import { ProgressTracker } from "@/components/translation/progress-tracker";
import { ResultTable } from "@/components/translation/result-table";
import { ConsistencyPanel } from "@/components/translation/consistency-panel";
import { QualityScore } from "@/components/translation/quality-score";
import { toast } from "sonner";

const statusConfig: Record<
  string,
  { label: string; variant: "default" | "secondary" | "destructive" | "outline"; icon: React.ElementType }
> = {
  pending: { label: "Pending", variant: "outline", icon: Clock },
  in_progress: { label: "In Progress", variant: "secondary", icon: Loader2 },
  completed: { label: "Completed", variant: "default", icon: CheckCircle2 },
  failed: { label: "Failed", variant: "destructive", icon: AlertCircle },
  cancelled: { label: "Cancelled", variant: "outline", icon: XCircle },
};

export default function JobDetailPage({
  params,
}: {
  params: Promise<{ jobId: string }>;
}) {
  const { jobId } = use(params);
  const { data: job, isLoading } = useJobStatus(jobId);
  const cancelMutation = useCancelJob();

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!job) {
    return (
      <div className="flex h-40 items-center justify-center text-muted-foreground">
        Job not found.
      </div>
    );
  }

  const config = statusConfig[job.status] || statusConfig.pending;
  const StatusIcon = config.icon;
  const averageScore =
    job.response?.translations
      .filter((t) => t.quality_score !== null)
      .reduce((sum, t, _, arr) => sum + (t.quality_score || 0) / arr.length, 0) ?? null;

  const handleCancel = () => {
    cancelMutation.mutate(jobId, {
      onSuccess: () => toast.success("Job cancelled"),
      onError: (err) => toast.error(err.message),
    });
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">
            Job Details
          </h1>
          <p className="text-sm text-muted-foreground mt-1 font-mono">
            {job.job_id}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant={config.variant} className="gap-1">
            <StatusIcon
              className={`h-3 w-3 ${job.status === "in_progress" ? "animate-spin" : ""}`}
            />
            {config.label}
          </Badge>
          {(job.status === "pending" || job.status === "in_progress") && (
            <Button
              variant="destructive"
              size="sm"
              onClick={handleCancel}
              disabled={cancelMutation.isPending}
            >
              Cancel
            </Button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Created
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">
              {new Date(job.created_at).toLocaleString()}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Latency
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">
              {job.response
                ? `${(job.response.total_latency_ms / 1000).toFixed(1)}s`
                : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Avg Quality Score
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              <QualityScore
                score={averageScore ? Math.round(averageScore) : null}
                size="md"
              />
            </div>
          </CardContent>
        </Card>
      </div>

      {(job.status === "pending" || job.status === "in_progress") && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Progress</CardTitle>
          </CardHeader>
          <CardContent>
            <ProgressTracker progress={job.progress} status={job.status} />
          </CardContent>
        </Card>
      )}

      {job.error && (
        <Card className="border-destructive">
          <CardHeader>
            <CardTitle className="text-base text-destructive">Error</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm">{job.error}</p>
          </CardContent>
        </Card>
      )}

      {job.response && (
        <>
          {job.response.source_text_1 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Source Text</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <p className="text-sm">{job.response.source_text_1}</p>
                {job.response.source_text_2 && (
                  <div>
                    <p className="text-xs text-muted-foreground mb-1">
                      Chinese Reference
                    </p>
                    <p className="text-sm">{job.response.source_text_2}</p>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Translation Results</CardTitle>
            </CardHeader>
            <CardContent>
              <ResultTable items={job.response.translations} />
            </CardContent>
          </Card>

          <ConsistencyPanel
            results={job.response.consistency_pair_results}
            overallPassed={job.response.consistency_passed}
          />
        </>
      )}
    </div>
  );
}
