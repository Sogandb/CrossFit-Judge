"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { History, Loader2, CheckCircle2, XCircle } from "lucide-react";
import type { JobInfo } from "./types";
import { faDateTime } from "@/lib/fa";

interface Props {
  jobs: JobInfo[];
  onSelect: (id: string) => void;
  activeId?: string;
}

export function HistoryList({ jobs, onSelect, activeId }: Props) {
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-lg font-bold">
          <History className="h-5 w-5" />
          تحلیل‌های اخیر
        </CardTitle>
      </CardHeader>
      <CardContent>
        {jobs.length === 0 ? (
          <p className="py-4 text-center text-sm text-muted-foreground">
            هنوز تحلیلی ثبت نشده است.
          </p>
        ) : (
          <ul className="divide-y">
            {jobs.map((j) => (
              <li key={j.id}>
                <button
                  onClick={() => onSelect(j.id)}
                  className={`flex w-full items-center justify-between gap-3 py-2.5 text-right
                              hover:bg-zinc-50 ${activeId === j.id ? "bg-red-50/60" : ""}`}
                >
                  <div className="min-w-0">
                    <div className="truncate font-medium">
                      {j.athlete_name || j.id}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {faDateTime(j.created_at)}
                    </div>
                  </div>
                  {j.status === "done" ? (
                    <Badge className="gap-1 bg-green-600 hover:bg-green-600">
                      <CheckCircle2 className="h-3 w-3" /> تکمیل
                    </Badge>
                  ) : j.status === "failed" ? (
                    <Badge variant="destructive" className="gap-1">
                      <XCircle className="h-3 w-3" /> خطا
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="gap-1">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      {j.stage_fa}
                    </Badge>
                  )}
                </button>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
