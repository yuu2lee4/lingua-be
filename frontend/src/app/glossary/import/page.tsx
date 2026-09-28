import { ImportDialog } from "@/components/glossary/import-dialog";

export default function ImportPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">Import Glossary</h1>
      <p className="text-muted-foreground">
        Upload a CSV or JSON file to import glossary terms in bulk.
      </p>
      <ImportDialog />
    </div>
  );
}
