"use client";

import * as React from "react";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Info } from "lucide-react";
import { cn } from "@/lib/utils";

interface InfoSection {
  label: string;
  content: string;
}

export interface InfoTooltipProps {
  /** Main title/name of the indicator */
  title?: string;
  /** Brief one-line description */
  description?: string;
  /** How the indicator is calculated */
  calculation?: string;
  /** Where the data comes from */
  source?: string;
  /** Update frequency */
  frequency?: string;
  /** Additional sections for detailed info */
  sections?: InfoSection[];
  /** How to interpret the values */
  interpretation?: string;
  /** Size of the info icon */
  size?: "xs" | "sm" | "md";
  /** Additional className for the icon */
  className?: string;
  /** Side for tooltip placement */
  side?: "top" | "right" | "bottom" | "left";
}

const sizeClasses = {
  xs: "h-3 w-3",
  sm: "h-3.5 w-3.5",
  md: "h-4 w-4",
};

export function InfoTooltip({
  title,
  description,
  calculation,
  source,
  frequency,
  sections,
  interpretation,
  size = "sm",
  className,
  side = "top",
}: InfoTooltipProps) {
  const hasContent = title || description || calculation || source || frequency || sections?.length || interpretation;
  
  if (!hasContent) return null;

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center justify-center rounded-full text-muted-foreground/60",
            "hover:text-muted-foreground hover:bg-muted/50 transition-colors",
            "focus:outline-none focus-visible:ring-1 focus-visible:ring-ring",
            "p-0.5 -m-0.5 cursor-help",
            className
          )}
          aria-label={`Info about ${title || "this indicator"}`}
        >
          <Info className={sizeClasses[size]} />
        </button>
      </TooltipTrigger>
      <TooltipContent 
        side={side} 
        className="max-w-[350px] p-0 overflow-hidden"
        sideOffset={8}
      >
        <div className="space-y-0">
          {/* Header */}
          {(title || description) && (
            <div className="px-3 py-2 border-b border-border/50 bg-muted/30">
              {title && (
                <p className="font-semibold text-sm text-foreground">{title}</p>
              )}
              {description && (
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">
                  {description}
                </p>
              )}
            </div>
          )}

          {/* Body */}
          <div className="px-3 py-2 space-y-2.5 text-xs">
            {calculation && (
              <InfoRow label="Calculation" content={calculation} />
            )}
            
            {source && (
              <InfoRow label="Source" content={source} />
            )}
            
            {frequency && (
              <InfoRow label="Frequency" content={frequency} />
            )}

            {sections?.map((section, idx) => (
              <InfoRow key={idx} label={section.label} content={section.content} />
            ))}

            {interpretation && (
              <div className="pt-1 border-t border-border/30">
                <p className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground mb-1">
                  Interpretation
                </p>
                <p className="text-muted-foreground leading-relaxed">
                  {interpretation}
                </p>
              </div>
            )}
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

function InfoRow({ label, content }: { label: string; content: string }) {
  return (
    <div className="grid grid-cols-[80px_1fr] gap-2 items-start">
      <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground pt-0.5">
        {label}
      </span>
      <span className="text-muted-foreground leading-relaxed">{content}</span>
    </div>
  );
}

// Convenience component for inline info with text
interface InfoWithLabelProps extends InfoTooltipProps {
  label: string;
  labelClassName?: string;
}

export function InfoWithLabel({ 
  label, 
  labelClassName,
  ...infoProps 
}: InfoWithLabelProps) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={labelClassName}>{label}</span>
      <InfoTooltip {...infoProps} />
    </span>
  );
}

