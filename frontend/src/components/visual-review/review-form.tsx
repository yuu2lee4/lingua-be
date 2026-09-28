"use client";

import { useForm } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
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
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Eye } from "lucide-react";
import { LANGUAGES } from "@/lib/utils/languages";
import type { VisualReviewResponse } from "@/types/visual-review";
import { useSubmitVisualReview } from "@/lib/hooks/use-visual-review";
import { toast } from "sonner";

const reviewSchema = z.object({
  target_langs: z.array(z.string()).min(1, "Select at least one language"),
  base_url: z.string().url("Must be a valid URL"),
  url_path: z.string(),
  reference_lang: z.string(),
  scroll_positions: z.number().min(0).max(10),
  sandbox_resolution: z.string(),
});

type ReviewFormValues = z.infer<typeof reviewSchema>;

const targetLanguages = Object.entries(LANGUAGES).filter(
  ([code]) => code !== "en-US"
);

interface ReviewFormProps {
  onResult: (data: VisualReviewResponse) => void;
}

export function ReviewForm({ onResult }: ReviewFormProps) {
  const mutation = useSubmitVisualReview();

  const form = useForm<ReviewFormValues>({
    resolver: zodResolver(reviewSchema),
    defaultValues: {
      target_langs: [],
      base_url: "https://www.example.com",
      url_path: "/ai",
      reference_lang: "en-US",
      scroll_positions: 1,
      sandbox_resolution: "1920x1080",
    },
  });

  const onSubmit = (values: ReviewFormValues) => {
    mutation.mutate(values, {
      onSuccess: (data) => {
        toast.success("Visual review completed");
        onResult(data);
      },
      onError: (err) => toast.error(err.message),
    });
  };

  const selectedLangs = form.watch("target_langs");

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <FormField
            control={form.control}
            name="base_url"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Base URL</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="url_path"
            render={({ field }) => (
              <FormItem>
                <FormLabel>URL Path</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="reference_lang"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Reference Language</FormLabel>
                <FormControl>
                  <Input {...field} />
                </FormControl>
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="scroll_positions"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Scroll Positions (0-10)</FormLabel>
                <FormControl>
                  <Input
                    type="number"
                    min={0}
                    max={10}
                    value={field.value}
                    onChange={(e) => field.onChange(Number(e.target.value))}
                  />
                </FormControl>
              </FormItem>
            )}
          />
          <FormField
            control={form.control}
            name="sandbox_resolution"
            render={({ field }) => (
              <FormItem>
                <FormLabel>Resolution</FormLabel>
                <FormControl>
                  <Input placeholder="1920x1080" {...field} />
                </FormControl>
                <FormDescription>Format: widthxheight</FormDescription>
              </FormItem>
            )}
          />
        </div>

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

        <Button type="submit" disabled={mutation.isPending} className="w-full sm:w-auto">
          <Eye className="mr-2 h-4 w-4" />
          {mutation.isPending ? "Reviewing..." : "Start Visual Review"}
        </Button>
      </form>
    </Form>
  );
}
