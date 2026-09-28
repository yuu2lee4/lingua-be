"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
import { useRouter } from "next/navigation";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import { ChevronDown, Send } from "lucide-react";
import { useSubmitTranslation } from "@/lib/hooks/use-translation";
import { LANGUAGES } from "@/lib/utils/languages";
import { toast } from "sonner";

const translationSchema = z.object({
  source_text_1: z.string().min(1, "Source text is required"),
  source_text_2: z.string().optional(),
  key: z.string().optional(),
  target_langs: z.array(z.string()).min(1, "Select at least one target language"),
  translation_model: z.string().optional(),
  review_model: z.string().optional(),
  quality_threshold: z.number().min(0).max(100).optional(),
  max_retries: z.number().min(0).max(5).optional(),
});

type TranslationFormValues = z.infer<typeof translationSchema>;

const targetLanguages = Object.entries(LANGUAGES).filter(
  ([code]) => code !== "en-US"
);

export function SubmitForm() {
  const router = useRouter();
  const [showAdvanced, setShowAdvanced] = useState(false);
  const mutation = useSubmitTranslation();

  const form = useForm<TranslationFormValues>({
    resolver: zodResolver(translationSchema),
    defaultValues: {
      source_text_1: "",
      source_text_2: "",
      key: "",
      target_langs: [],
      translation_model: "",
      review_model: "",
    },
  });

  const onSubmit = (values: TranslationFormValues) => {
    const payload = {
      ...values,
      source_text_2: values.source_text_2 || undefined,
      key: values.key || undefined,
      translation_model: values.translation_model || undefined,
      review_model: values.review_model || undefined,
      quality_threshold: values.quality_threshold ?? undefined,
      max_retries: values.max_retries ?? undefined,
    };

    mutation.mutate(payload, {
      onSuccess: (data) => {
        toast.success(`Job submitted: ${data.job_id}`);
        router.push(`/translations/${data.job_id}`);
      },
      onError: (err) => toast.error(err.message),
    });
  };

  const selectedLangs = form.watch("target_langs");

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <FormField
          control={form.control}
          name="source_text_1"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Source Text (English)</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="Enter the English text to translate..."
                  className="min-h-[120px] resize-y"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="source_text_2"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Reference Text (Chinese, optional)</FormLabel>
              <FormControl>
                <Textarea
                  placeholder="Enter Chinese reference text for dual-source translation..."
                  className="min-h-[80px] resize-y"
                  {...field}
                />
              </FormControl>
              <FormDescription>
                Providing a Chinese reference can improve translation quality for CJK languages.
              </FormDescription>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="key"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Key (optional)</FormLabel>
              <FormControl>
                <Input placeholder="e.g., homepage.hero.title" {...field} />
              </FormControl>
              <FormDescription>
                Text identifier key for tracking purposes.
              </FormDescription>
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="target_langs"
          render={() => (
            <FormItem>
              <FormLabel>
                Target Languages ({selectedLangs.length} selected)
              </FormLabel>
              <div className="flex gap-2 mb-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    form.setValue(
                      "target_langs",
                      targetLanguages.map(([code]) => code)
                    )
                  }
                >
                  Select All
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => form.setValue("target_langs", [])}
                >
                  Clear
                </Button>
              </div>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
                {targetLanguages.map(([code, lang]) => (
                  <FormField
                    key={code}
                    control={form.control}
                    name="target_langs"
                    render={({ field }) => (
                      <FormItem className="flex items-center gap-2 space-y-0">
                        <FormControl>
                          <Checkbox
                            checked={field.value?.includes(code)}
                            onCheckedChange={(checked) => {
                              const current = field.value || [];
                              field.onChange(
                                checked
                                  ? [...current, code]
                                  : current.filter((c: string) => c !== code)
                              );
                            }}
                          />
                        </FormControl>
                        <FormLabel className="text-sm font-normal cursor-pointer">
                          {lang.nameEn}
                        </FormLabel>
                      </FormItem>
                    )}
                  />
                ))}
              </div>
              <FormMessage />
            </FormItem>
          )}
        />

        <Collapsible open={showAdvanced} onOpenChange={setShowAdvanced}>
          <CollapsibleTrigger asChild>
            <Button variant="ghost" size="sm" type="button" className="gap-1">
              <ChevronDown
                className={`h-4 w-4 transition-transform ${showAdvanced ? "rotate-180" : ""}`}
              />
              Advanced Options
            </Button>
          </CollapsibleTrigger>
          <CollapsibleContent className="space-y-4 pt-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <FormField
                control={form.control}
                name="translation_model"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Translation Model</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., claude-opus-4-6" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="review_model"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Review Model</FormLabel>
                    <FormControl>
                      <Input placeholder="e.g., gpt-5.2" {...field} />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="quality_threshold"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Quality Threshold (0-100)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={0}
                        max={100}
                        placeholder="90"
                        value={field.value ?? ""}
                        onChange={(e) =>
                          field.onChange(
                            e.target.value === ""
                              ? undefined
                              : Number(e.target.value)
                          )
                        }
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="max_retries"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Max Retries (0-5)</FormLabel>
                    <FormControl>
                      <Input
                        type="number"
                        min={0}
                        max={5}
                        placeholder="2"
                        value={field.value ?? ""}
                        onChange={(e) =>
                          field.onChange(
                            e.target.value === ""
                              ? undefined
                              : Number(e.target.value)
                          )
                        }
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>
          </CollapsibleContent>
        </Collapsible>

        <Button type="submit" disabled={mutation.isPending} className="w-full sm:w-auto">
          <Send className="mr-2 h-4 w-4" />
          {mutation.isPending ? "Submitting..." : "Submit Translation"}
        </Button>
      </form>
    </Form>
  );
}
