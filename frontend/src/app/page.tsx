import Link from "next/link";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  BookOpen,
  Languages,
  Eye,
  Plus,
  Upload,
  ArrowRight,
} from "lucide-react";

export default function DashboardPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground mt-1">
          AI Translation Platform — manage glossaries, submit translations, and
          review visual quality.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Glossary</CardTitle>
            <BookOpen className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <CardDescription>
              Manage terminology across 14 languages with L1 Match + L2 Business
              glossary system.
            </CardDescription>
            <Button asChild variant="link" className="mt-2 p-0 h-auto">
              <Link href="/glossary">
                View Terms <ArrowRight className="ml-1 h-3 w-3" />
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Translations</CardTitle>
            <Languages className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <CardDescription>
              Submit texts for AI-powered multi-language translation with quality
              review and consistency checks.
            </CardDescription>
            <Button asChild variant="link" className="mt-2 p-0 h-auto">
              <Link href="/translations">
                Manage Jobs <ArrowRight className="ml-1 h-3 w-3" />
              </Link>
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Visual Review</CardTitle>
            <Eye className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <CardDescription>
              Automated visual comparison of translated pages to catch layout,
              rendering, and translation issues.
            </CardDescription>
            <Button asChild variant="link" className="mt-2 p-0 h-auto">
              <Link href="/visual-review">
                Start Review <ArrowRight className="ml-1 h-3 w-3" />
              </Link>
            </Button>
          </CardContent>
        </Card>
      </div>

      <div>
        <h2 className="text-lg font-semibold mb-4">Quick Actions</h2>
        <div className="flex flex-wrap gap-3">
          <Button asChild>
            <Link href="/translations/new">
              <Plus className="mr-2 h-4 w-4" />
              New Translation
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/glossary/import">
              <Upload className="mr-2 h-4 w-4" />
              Import Glossary
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/glossary/candidates">
              <BookOpen className="mr-2 h-4 w-4" />
              Review Candidates
            </Link>
          </Button>
        </div>
      </div>
    </div>
  );
}
