"use client";

import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Check, X } from "lucide-react";
import { useReviewCandidate } from "@/lib/hooks/use-glossary";
import { toast } from "sonner";
import type { GlossaryCandidateResponse } from "@/types/glossary";
import { getLanguageName } from "@/lib/utils/languages";

interface CandidateCardProps {
  candidate: GlossaryCandidateResponse;
}

const statusColors: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  pending: "outline",
  approved: "default",
  rejected: "destructive",
  migrated: "secondary",
};

export function CandidateCard({ candidate }: CandidateCardProps) {
  const reviewMutation = useReviewCandidate();

  const handleReview = (action: "approved" | "rejected") => {
    reviewMutation.mutate(
      {
        candidateId: candidate.id,
        data: {
          action,
          migrate_to_business: action === "approved",
        },
      },
      {
        onSuccess: () => {
          toast.success(
            action === "approved" ? "Candidate approved" : "Candidate rejected"
          );
        },
        onError: (err) => toast.error(err.message),
      }
    );
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-lg">{candidate.term_en}</h3>
          <Badge variant={statusColors[candidate.status]} className="capitalize">
            {candidate.status}
          </Badge>
        </div>
        {candidate.definition && (
          <p className="text-sm text-muted-foreground">{candidate.definition}</p>
        )}
      </CardHeader>
      <CardContent className="pb-3">
        {Object.keys(candidate.translations).length > 0 && (
          <div className="space-y-1">
            <p className="text-xs font-medium text-muted-foreground mb-2">
              AI Suggested Translations
            </p>
            <div className="grid grid-cols-1 gap-1 sm:grid-cols-2">
              {Object.entries(candidate.translations).map(([lang, translation]) => (
                <div
                  key={lang}
                  className="flex items-center gap-2 text-sm rounded-md bg-muted px-2 py-1"
                >
                  <span className="text-xs font-medium text-muted-foreground w-20 shrink-0">
                    {getLanguageName(lang)}
                  </span>
                  <span className="truncate">{translation}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="flex gap-4 mt-3 text-xs text-muted-foreground">
          <span>Source: {candidate.source}</span>
          {candidate.part_of_speech && (
            <span>POS: {candidate.part_of_speech}</span>
          )}
        </div>
      </CardContent>
      {candidate.status === "pending" && (
        <CardFooter className="gap-2">
          <Button
            size="sm"
            onClick={() => handleReview("approved")}
            disabled={reviewMutation.isPending}
          >
            <Check className="mr-1 h-4 w-4" />
            Approve
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => handleReview("rejected")}
            disabled={reviewMutation.isPending}
          >
            <X className="mr-1 h-4 w-4" />
            Reject
          </Button>
        </CardFooter>
      )}
    </Card>
  );
}
