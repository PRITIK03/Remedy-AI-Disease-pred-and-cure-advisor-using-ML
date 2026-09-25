"use client";

import type { ReactNode } from "react";

import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Input } from "@/components/ui/input";

import { cn } from "@/lib/utils";
import type { FieldOption } from "@/lib/labels";

interface BaseFieldProps {
  name: string;
  label: string;
  error?: string;
  hint?: string;
  children: ReactNode;
}

export function FormFieldWrapper({ name, label, error, hint, children }: BaseFieldProps) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={name} className="text-sm font-medium">
        {label}
      </Label>
      {children}
      {hint && !error && (
        <p id={`${name}-hint`} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p
          id={`${name}-error`}
          role="alert"
          className="text-xs font-medium text-destructive"
        >
          {error}
        </p>
      )}
    </div>
  );
}

interface NumberFieldProps {
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string;
  hint?: string;
  unit?: string;
  min?: number;
  max?: number;
  step?: string;
}

export function NumberField({
  name,
  label,
  value,
  onChange,
  error,
  hint,
  unit,
  min,
  max,
  step = "1",
}: NumberFieldProps) {
  return (
    <FormFieldWrapper name={name} label={label} error={error} hint={hint}>
      <div className="relative">
        <Input
          id={name}
          name={name}
          type="number"
          inputMode="decimal"
          step={step}
          min={min}
          max={max}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          aria-invalid={!!error}
          aria-describedby={error ? `${name}-error` : hint ? `${name}-hint` : undefined}
          className={cn("pr-14", error && "border-destructive focus-visible:ring-destructive")}
        />
        {unit && (
          <span
            className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-xs text-muted-foreground"
            aria-hidden="true"
          >
            {unit}
          </span>
        )}
      </div>
    </FormFieldWrapper>
  );
}

interface RadioFieldProps {
  name: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: FieldOption[];
  error?: string;
  hint?: string;
}

export function RadioField({
  name,
  label,
  value,
  onChange,
  options,
  error,
  hint,
}: RadioFieldProps) {
  return (
    <FormFieldWrapper name={name} label={label} error={error} hint={hint}>
      <RadioGroup
        name={name}
        value={value}
        onValueChange={onChange}
        aria-invalid={!!error}
        aria-describedby={error ? `${name}-error` : hint ? `${name}-hint` : undefined}
        className={cn("flex flex-wrap gap-x-4 gap-y-2", error && "text-destructive")}
      >
        {options.map((option) => (
          <div key={option.value} className="flex items-center gap-2">
            <RadioGroupItem value={String(option.value)} id={`${name}-${option.value}`} />
            <Label
              htmlFor={`${name}-${option.value}`}
              className="cursor-pointer font-normal peer-disabled:cursor-not-allowed"
              title={option.description}
            >
              {option.label}
            </Label>
          </div>
        ))}
      </RadioGroup>
    </FormFieldWrapper>
  );
}
