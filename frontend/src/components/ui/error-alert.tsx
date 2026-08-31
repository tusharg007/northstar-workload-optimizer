import * as React from "react"
import { AlertCircle } from "lucide-react"
import { Button } from "./button"
import { cn } from "@/lib/utils"

interface ErrorAlertProps {
  message: string
  onRetry?: () => void
  className?: string
}

export function ErrorAlert({ message, onRetry, className }: ErrorAlertProps) {
  return (
    <div className={cn("flex flex-col gap-4 rounded-md border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/50", className)}>
      <div className="flex items-start gap-3">
        <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mt-0.5" />
        <div className="flex-1 text-sm text-red-800 dark:text-red-300">
          {message}
        </div>
      </div>
      {onRetry && (
        <div className="flex justify-end">
          <Button variant="outline" size="sm" onClick={onRetry} className="border-red-200 text-red-700 hover:bg-red-100 hover:text-red-800 dark:border-red-900 dark:text-red-400 dark:hover:bg-red-900/50">
            Retry
          </Button>
        </div>
      )}
    </div>
  )
}
