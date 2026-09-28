import { SubmitForm } from "@/components/translation/submit-form";

export default function NewTranslationPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <h1 className="text-3xl font-bold tracking-tight">New Translation</h1>
      <p className="text-muted-foreground">
        Submit text for multi-language translation with quality review.
      </p>
      <SubmitForm />
    </div>
  );
}
