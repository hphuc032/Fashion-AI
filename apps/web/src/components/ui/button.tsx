import type { ButtonHTMLAttributes } from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const variants = cva("button", {
  variants: {
    variant: { primary: "button-primary", secondary: "button-secondary" },
  },
  defaultVariants: { variant: "secondary" },
});
export function Button({
  className,
  variant,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof variants>) {
  return (
    <button
      data-slot="button"
      className={cn(variants({ variant }), className)}
      {...props}
    />
  );
}
