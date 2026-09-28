"use client";

import { useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getExpandedRowModel,
  flexRender,
  type ColumnDef,
  type ExpandedState,
} from "@tanstack/react-table";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ChevronRight, MoreHorizontal, Pencil, Trash2 } from "lucide-react";
import type { GlossaryTermResponse } from "@/types/glossary";
import { TranslationCell } from "./translation-cell";
import { LANGUAGES } from "@/lib/utils/languages";

const statusVariant: Record<string, "default" | "secondary" | "outline"> = {
  active: "default",
  inactive: "secondary",
  pending: "outline",
};

const sourceLabels: Record<string, string> = {
  manual: "Manual",
  ai_extracted: "AI Extracted",
  imported: "Imported",
};

interface TermTableProps {
  data: GlossaryTermResponse[];
  onEdit: (term: GlossaryTermResponse) => void;
  onDelete: (termId: string) => void;
}

export function TermTable({ data, onEdit, onDelete }: TermTableProps) {
  const [expanded, setExpanded] = useState<ExpandedState>({});

  const columns: ColumnDef<GlossaryTermResponse>[] = [
    {
      id: "expander",
      header: () => null,
      cell: ({ row }) => (
        <Button
          variant="ghost"
          size="sm"
          className="h-8 w-8 p-0"
          onClick={() => row.toggleExpanded()}
        >
          <ChevronRight
            className={`h-4 w-4 transition-transform ${
              row.getIsExpanded() ? "rotate-90" : ""
            }`}
          />
        </Button>
      ),
      size: 40,
    },
    {
      accessorKey: "term_en",
      header: "English Term",
      cell: ({ row }) => (
        <span className="font-medium">{row.getValue("term_en")}</span>
      ),
    },
    {
      accessorKey: "definition",
      header: "Definition",
      cell: ({ row }) => (
        <span className="max-w-[300px] truncate block text-muted-foreground">
          {row.getValue("definition") || "—"}
        </span>
      ),
    },
    {
      accessorKey: "part_of_speech",
      header: "POS",
      cell: ({ row }) => row.getValue("part_of_speech") || "—",
      size: 80,
    },
    {
      accessorKey: "do_not_translate",
      header: "DNT",
      cell: ({ row }) =>
        row.getValue("do_not_translate") ? (
          <Badge variant="destructive" className="text-xs">
            DNT
          </Badge>
        ) : null,
      size: 60,
    },
    {
      accessorKey: "source",
      header: "Source",
      cell: ({ row }) => (
        <Badge variant="outline" className="text-xs">
          {sourceLabels[row.getValue("source") as string] ||
            row.getValue("source")}
        </Badge>
      ),
      size: 100,
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => {
        const status = row.getValue("status") as string;
        return (
          <Badge variant={statusVariant[status] || "outline"} className="text-xs capitalize">
            {status}
          </Badge>
        );
      },
      size: 80,
    },
    {
      id: "actions",
      header: () => null,
      cell: ({ row }) => (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="h-8 w-8 p-0">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onEdit(row.original)}>
              <Pencil className="mr-2 h-4 w-4" />
              Edit
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={() => onDelete(row.original.term_id)}
              className="text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      ),
      size: 40,
    },
  ];

  const table = useReactTable({
    data,
    columns,
    state: { expanded },
    onExpandedChange: setExpanded,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    getRowCanExpand: () => true,
  });

  return (
    <div className="rounded-md border">
      <Table>
        <TableHeader>
          {table.getHeaderGroups().map((headerGroup) => (
            <TableRow key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <TableHead key={header.id} style={{ width: header.getSize() !== 150 ? header.getSize() : undefined }}>
                  {header.isPlaceholder
                    ? null
                    : flexRender(
                        header.column.columnDef.header,
                        header.getContext()
                      )}
                </TableHead>
              ))}
            </TableRow>
          ))}
        </TableHeader>
        <TableBody>
          {table.getRowModel().rows?.length ? (
            table.getRowModel().rows.map((row) => (
              <>
                <TableRow key={row.id}>
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </TableCell>
                  ))}
                </TableRow>
                {row.getIsExpanded() && (
                  <TableRow key={`${row.id}-expanded`}>
                    <TableCell colSpan={columns.length} className="bg-muted/50 p-4">
                      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
                        {Object.entries(LANGUAGES)
                          .filter(([code]) => code !== "en-US")
                          .map(([code, lang]) => (
                            <TranslationCell
                              key={code}
                              termId={row.original.term_id}
                              langCode={code}
                              langName={lang.nameEn}
                              value={row.original.translations[code] || ""}
                            />
                          ))}
                      </div>
                    </TableCell>
                  </TableRow>
                )}
              </>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={columns.length} className="h-24 text-center">
                No terms found.
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </div>
  );
}
