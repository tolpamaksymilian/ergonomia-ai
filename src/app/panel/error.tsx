"use client";

import { DashboardError } from "@/components/dashboard/dashboard-error";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) { return <DashboardError reset={reset} />; }
