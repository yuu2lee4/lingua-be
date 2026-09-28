"use client";

import { useForm } from "react-hook-form";
import { z } from "zod/v4";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useCreateTerm, useUpdateTerm } from "@/lib/hooks/use-glossary";
import { LANGUAGES } from "@/lib/utils/languages";
import { toast } from "sonner";
import type { GlossaryTermResponse } from "@/types/glossary";

const termSchema = z.object({
  term_en: z.string().min(1, "English term is required").max(512),
  definition: z.string().max(2000),
  part_of_speech: z.string().max(32),
  do_not_translate: z.boolean(),
  translations: z.record(z.string(), z.string()),
});

type TermFormValues = z.infer<typeof termSchema>;

interface TermFormProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  editTerm?: GlossaryTermResponse | null;
}

export function TermForm({ open, onOpenChange, editTerm }: TermFormProps) {
  const createMutation = useCreateTerm();
  const updateMutation = useUpdateTerm();
  const isEditing = !!editTerm;

  const form = useForm<TermFormValues>({
    resolver: zodResolver(termSchema),
    defaultValues: editTerm
      ? {
          term_en: editTerm.term_en,
          definition: editTerm.definition,
          part_of_speech: editTerm.part_of_speech,
          do_not_translate: editTerm.do_not_translate,
          translations: editTerm.translations,
        }
      : {
          term_en: "",
          definition: "",
          part_of_speech: "",
          do_not_translate: false,
          translations: {},
        },
  });

  const onSubmit = (values: TermFormValues) => {
    if (isEditing) {
      updateMutation.mutate(
        {
          termId: editTerm.term_id,
          data: {
            definition: values.definition,
            part_of_speech: values.part_of_speech,
            do_not_translate: values.do_not_translate,
          },
        },
        {
          onSuccess: () => {
            toast.success("Term updated");
            onOpenChange(false);
            form.reset();
          },
          onError: (err) => toast.error(err.message),
        }
      );
    } else {
      createMutation.mutate(values, {
        onSuccess: () => {
          toast.success("Term created");
          onOpenChange(false);
          form.reset();
        },
        onError: (err) => toast.error(err.message),
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[85vh]">
        <DialogHeader>
          <DialogTitle>{isEditing ? "Edit Term" : "Create Term"}</DialogTitle>
        </DialogHeader>
        <ScrollArea className="max-h-[70vh] pr-4">
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="term_en"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>English Term</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="Enter English term"
                        {...field}
                        disabled={isEditing}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="definition"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Definition</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Term definition"
                        className="resize-none"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <div className="flex gap-4">
                <FormField
                  control={form.control}
                  name="part_of_speech"
                  render={({ field }) => (
                    <FormItem className="flex-1">
                      <FormLabel>Part of Speech</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g., noun, verb" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="do_not_translate"
                  render={({ field }) => (
                    <FormItem className="flex items-center gap-2 pt-6">
                      <FormControl>
                        <Switch
                          checked={field.value}
                          onCheckedChange={field.onChange}
                        />
                      </FormControl>
                      <FormLabel className="!mt-0">Do Not Translate</FormLabel>
                    </FormItem>
                  )}
                />
              </div>

              {!isEditing && (
                <div className="space-y-3">
                  <FormLabel>Translations</FormLabel>
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {Object.entries(LANGUAGES)
                      .filter(([code]) => code !== "en-US")
                      .map(([code, lang]) => (
                        <FormField
                          key={code}
                          control={form.control}
                          name={`translations.${code}`}
                          render={({ field }) => (
                            <FormItem>
                              <div className="flex items-center gap-2">
                                <span className="w-16 text-xs text-muted-foreground shrink-0">
                                  {lang.nameEn}
                                </span>
                                <FormControl>
                                  <Input
                                    placeholder={`${lang.nameEn} translation`}
                                    className="h-8 text-sm"
                                    {...field}
                                    value={field.value || ""}
                                  />
                                </FormControl>
                              </div>
                            </FormItem>
                          )}
                        />
                      ))}
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-4">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => onOpenChange(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={
                    createMutation.isPending || updateMutation.isPending
                  }
                >
                  {createMutation.isPending || updateMutation.isPending
                    ? "Saving..."
                    : isEditing
                      ? "Update"
                      : "Create"}
                </Button>
              </div>
            </form>
          </Form>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
