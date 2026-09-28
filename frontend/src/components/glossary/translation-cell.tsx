"use client";

import { useState, useRef, useEffect } from "react";
import { Input } from "@/components/ui/input";
import { useUpdateTermTranslation } from "@/lib/hooks/use-glossary";
import { toast } from "sonner";

interface TranslationCellProps {
  termId: string;
  langCode: string;
  langName: string;
  value: string;
}

export function TranslationCell({
  termId,
  langCode,
  langName,
  value,
}: TranslationCellProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);
  const mutation = useUpdateTermTranslation();

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isEditing]);

  useEffect(() => {
    setEditValue(value);
  }, [value]);

  const handleSave = () => {
    setIsEditing(false);
    if (editValue === value) return;
    if (!editValue.trim()) {
      setEditValue(value);
      return;
    }
    mutation.mutate(
      { termId, langCode, data: { translation: editValue.trim() } },
      {
        onError: () => {
          toast.error(`Failed to update ${langName} translation`);
          setEditValue(value);
        },
      }
    );
  };

  return (
    <div className="flex items-center gap-2 rounded-md border p-2 text-sm">
      <span className="w-12 shrink-0 text-xs font-medium text-muted-foreground uppercase">
        {langCode.split("-")[0]}
      </span>
      {isEditing ? (
        <Input
          ref={inputRef}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={handleSave}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleSave();
            if (e.key === "Escape") {
              setEditValue(value);
              setIsEditing(false);
            }
          }}
          className="h-7 text-sm"
        />
      ) : (
        <button
          onClick={() => setIsEditing(true)}
          className="w-full text-left truncate hover:text-primary cursor-text min-h-[28px]"
        >
          {value || (
            <span className="text-muted-foreground italic">Click to add</span>
          )}
        </button>
      )}
    </div>
  );
}
