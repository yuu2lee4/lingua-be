"use client";

import { useState, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Upload, FileText } from "lucide-react";
import { useImportTerms } from "@/lib/hooks/use-glossary";
import { toast } from "sonner";
import type { GlossaryTermCreate } from "@/types/glossary";

export function ImportDialog() {
  const [terms, setTerms] = useState<GlossaryTermCreate[]>([]);
  const [overwrite, setOverwrite] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);
  const importMutation = useImportTerms();

  const handleFileChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (!file) return;
      setFileName(file.name);

      const reader = new FileReader();
      reader.onload = (event) => {
        try {
          const content = event.target?.result as string;
          if (file.name.endsWith(".json")) {
            const parsed = JSON.parse(content);
            const items = Array.isArray(parsed) ? parsed : parsed.terms || [];
            setTerms(items);
          } else if (file.name.endsWith(".csv")) {
            const lines = content.split("\n").filter(Boolean);
            const headers = lines[0].split(",").map((h: string) => h.trim());
            const items = lines.slice(1).map((line: string) => {
              const values = line.split(",").map((v: string) => v.trim());
              const term: GlossaryTermCreate = { term_en: "" };
              headers.forEach((header: string, i: number) => {
                const value = values[i] || "";
                if (header === "term_en") term.term_en = value;
                else if (header === "definition") term.definition = value;
                else if (header === "part_of_speech") term.part_of_speech = value;
                else if (header === "do_not_translate")
                  term.do_not_translate = value === "true";
              });
              return term;
            });
            setTerms(items.filter((t: GlossaryTermCreate) => t.term_en));
          }
        } catch {
          toast.error("Failed to parse file");
        }
      };
      reader.readAsText(file);
    },
    []
  );

  const handleImport = () => {
    if (terms.length === 0) return;
    importMutation.mutate(
      { terms, overwrite },
      {
        onSuccess: (data) => {
          toast.success(
            `Imported ${data.imported} terms, skipped ${data.skipped}`
          );
          setTerms([]);
          setFileName(null);
        },
        onError: (err) => toast.error(err.message),
      }
    );
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Upload File</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <label className="flex flex-col items-center justify-center w-full h-40 border-2 border-dashed rounded-lg cursor-pointer hover:bg-muted/50 transition-colors">
            <div className="flex flex-col items-center gap-2">
              <Upload className="h-8 w-8 text-muted-foreground" />
              <span className="text-sm text-muted-foreground">
                Drop CSV or JSON file here, or click to browse
              </span>
              {fileName && (
                <span className="flex items-center gap-1 text-sm font-medium">
                  <FileText className="h-4 w-4" />
                  {fileName}
                </span>
              )}
            </div>
            <input
              type="file"
              accept=".csv,.json"
              className="hidden"
              onChange={handleFileChange}
            />
          </label>

          <div className="flex items-center gap-2">
            <Switch
              id="overwrite"
              checked={overwrite}
              onCheckedChange={setOverwrite}
            />
            <Label htmlFor="overwrite">Overwrite existing terms</Label>
          </div>
        </CardContent>
      </Card>

      {terms.length > 0 && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Preview ({terms.length} terms)</CardTitle>
            <Button
              onClick={handleImport}
              disabled={importMutation.isPending}
            >
              {importMutation.isPending ? "Importing..." : "Import All"}
            </Button>
          </CardHeader>
          <CardContent>
            <div className="rounded-md border max-h-[400px] overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>English Term</TableHead>
                    <TableHead>Definition</TableHead>
                    <TableHead>POS</TableHead>
                    <TableHead>DNT</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {terms.slice(0, 50).map((term, i) => (
                    <TableRow key={i}>
                      <TableCell className="font-medium">
                        {term.term_en}
                      </TableCell>
                      <TableCell className="max-w-[200px] truncate">
                        {term.definition || "—"}
                      </TableCell>
                      <TableCell>{term.part_of_speech || "—"}</TableCell>
                      <TableCell>{term.do_not_translate ? "Yes" : "No"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            {terms.length > 50 && (
              <p className="text-sm text-muted-foreground mt-2">
                Showing first 50 of {terms.length} terms
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
