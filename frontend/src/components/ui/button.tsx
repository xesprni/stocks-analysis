import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md text-[13px] font-medium tracking-tight transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/70 focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "border border-zinc-900 bg-zinc-900 text-zinc-50 shadow-[0_1px_0_rgba(255,255,255,0.12)_inset,0_1px_2px_rgba(0,0,0,0.12)] hover:bg-zinc-800",
        secondary: "border border-zinc-200 bg-zinc-100 text-zinc-900 shadow-sm hover:bg-zinc-200",
        ghost: "border border-transparent text-zinc-800 hover:bg-zinc-100",
        outline: "border border-zinc-300 bg-white text-zinc-900 shadow-[0_1px_0_rgba(255,255,255,0.7)_inset] hover:bg-zinc-100",
        destructive: "border border-red-700 bg-red-600 text-white shadow-sm hover:bg-red-500",
      },
      size: {
        default: "h-9 px-3.5",
        sm: "h-8 px-2.5 text-[12px]",
        lg: "h-10 px-5 text-sm",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />;
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
