"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";

export default function TranslationsPage() {
  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold tracking-tight">Translations</h1>
        <Button asChild>
          <Link href="/translations/new">
            <Plus className="mr-2 h-4 w-4" />
            New Translation
          </Link>
        </Button>
      </div>

      <div className="flex h-40 items-center justify-center rounded-md border border-dashed">
        <div className="text-center">
          <p className="text-muted-foreground">
            Submit a translation to see results here.
          </p>
          <Button asChild variant="link" className="mt-2">
            <Link href="/translations/new">Create your first translation</Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
