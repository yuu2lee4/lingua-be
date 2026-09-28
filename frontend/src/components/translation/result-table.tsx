"use client";

import { useState } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ChevronRight } from "lucide-react";
import { QualityScore } from "./quality-score";
import { getLanguageName } from "@/lib/utils/languages";
import type { TranslationItem } from "@/types/translation";

interface ResultTableProps {
  items: TranslationItem[];
}

export function ResultTable({ items }: ResultTableProps) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRow = (lang: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(lang)) next.delete(lang);
      else next.add(lang);
      return next;
    });
  };

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-8" />
            <TableHead>Language</TableHead>
            <TableHead>Translated Text</TableHead>
            <TableHead className="w-16 text-center">Score</TableHead>
            <TableHead className="w-16 text-center">Retries</TableHead>
            <TableHead className="w-20 text-right">Latency</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <>
              <TableRow key={item.target_lang}>
                <TableCell>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 p-0"
                    onClick={() => toggleRow(item.target_lang)}
                  >
                    <ChevronRight
                      className={`h-4 w-4 transition-transform ${
                        expandedRows.has(item.target_lang) ? "rotate-90" : ""
                      }`}
                    />
                  </Button>
                </TableCell>
                <TableCell>
                  <div>
                    <span className="font-medium">
                      {getLanguageName(item.target_lang)}
                    </span>
                    <span className="ml-2 text-xs text-muted-foreground">
                      {item.target_lang}
                    </span>
                  </div>
                </TableCell>
                <TableCell className="max-w-[400px]">
                  <p className="truncate">{item.translated_text}</p>
                </TableCell>
                <TableCell className="text-center">
                  <div className="flex justify-center">
                    <QualityScore score={item.quality_score} />
                  </div>
                </TableCell>
                <TableCell className="text-center">
                  {item.retry_count > 0 ? (
                    <Badge variant="outline">{item.retry_count}</Badge>
                  ) : (
                    "0"
                  )}
                </TableCell>
                <TableCell className="text-right text-sm text-muted-foreground">
                  {(item.latency_ms / 1000).toFixed(1)}s
                </TableCell>
              </TableRow>
              {expandedRows.has(item.target_lang) && (
                <TableRow key={`${item.target_lang}-detail`}>
                  <TableCell colSpan={6} className="bg-muted/50 p-4">
                    <div className="space-y-3">
                      <div>
                        <p className="text-sm font-medium mb-1">Full Translation</p>
                        <p className="text-sm bg-background p-3 rounded-md border">
                          {item.translated_text}
                        </p>
                      </div>

                      {item.quality_feedback && (
                        <div>
                          <p className="text-sm font-medium mb-1">
                            Quality Feedback
                          </p>
                          <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                            {item.quality_feedback}
                          </p>
                        </div>
                      )}

                      {item.glossary_terms_matched.length > 0 && (
                        <div>
                          <p className="text-sm font-medium mb-1">
                            Matched Glossary Terms
                          </p>
                          <div className="flex flex-wrap gap-1">
                            {item.glossary_terms_matched.map((term) => (
                              <Badge key={term} variant="secondary" className="text-xs">
                                {term}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}

                      {item.placeholder_issues.length > 0 && (
                        <div>
                          <p className="text-sm font-medium mb-1 text-destructive">
                            Placeholder Issues
                          </p>
                          <ul className="list-disc list-inside text-sm text-destructive">
                            {item.placeholder_issues.map((issue, i) => (
                              <li key={i}>{issue}</li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  </TableCell>
                </TableRow>
              )}
            </>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
