import * as React from "react"
import { LucideIcon } from "lucide-react"
import { Button } from "./button"
import { cn } from "@/lib/utils"

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description: string
  actionLabel?: string
  onAction?: () => void
  className?: string
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  onAction,
  className
}: EmptyStateProps) {
  return (
    <div className={cn("flex min-h-[300px] flex-col items-center justify-center rounded-xl border border-dashed p-8 text-center animate-in fade-in-50 dark:border-gray-800", className)}>
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-muted dark:bg-gray-800">
        <Icon className="h-6 w-6 text-muted-foreground dark:text-gray-400" />
      </div>
      <h3 className="mt-4 text-lg font-semibold dark:text-gray-50">{title}</h3>
      <p className="mt-2 text-sm text-muted-foreground max-w-sm mx-auto dark:text-gray-400">
        {description}
      </p>
      {actionLabel && onAction && (
        <Button onClick={onAction} className="mt-6">
          {actionLabel}
        </Button>
      )}
    </div>
  )
}
