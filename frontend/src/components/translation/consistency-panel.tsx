"use client";

import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronDown } from "lucide-react";
import { getLanguageName } from "@/lib/utils/languages";
import type { ConsistencyPairResult } from "@/types/translation";

interface ConsistencyPanelProps {
  results: ConsistencyPairResult[];
  overallPassed: boolean;
}

export function ConsistencyPanel({
  results,
  overallPassed,
}: ConsistencyPanelProps) {
  const [expandedPairs, setExpandedPairs] = useState<Set<string>>(new Set());

  if (results.length === 0) return null;

  const togglePair = (key: string) => {
    setExpandedPairs((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">Consistency Review</CardTitle>
          <Badge variant={overallPassed ? "default" : "destructive"}>
            {overallPassed ? "Passed" : "Failed"}
          </Badge>
        </div>
      </CardHeader>
      <CardContent>
        <div className="space-y-2">
          {results.map((pair) => {
            const key = `${pair.lang1}-${pair.lang2}`;
            const isExpanded = expandedPairs.has(key);
            return (
              <div key={key} className="rounded-md border">
                <Button
                  variant="ghost"
                  className="w-full justify-between px-3 py-2 h-auto"
                  onClick={() => togglePair(key)}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">
                      {getLanguageName(pair.lang1)} ↔{" "}
                      {getLanguageName(pair.lang2)}
                    </span>
                    <Badge
                      variant={pair.passed ? "outline" : "destructive"}
                      className="text-xs"
                    >
                      {pair.passed ? "Pass" : "Fail"}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className="text-xs text-muted-foreground">
                      {pair.checked_terms_count} checked
                      {pair.inconsistent_terms_count > 0 && (
                        <span className="text-destructive ml-1">
                          ({pair.inconsistent_terms_count} inconsistent)
                        </span>
                      )}
                    </span>
                    <ChevronDown
                      className={`h-4 w-4 transition-transform ${isExpanded ? "rotate-180" : ""}`}
                    />
                  </div>
                </Button>
                {isExpanded && pair.feedback && (
                  <div className="px-3 pb-3 text-sm text-muted-foreground whitespace-pre-wrap border-t pt-2">
                    {pair.feedback}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
}
