import * as React from "react";

import { cn } from "@/lib/utils";

const Table = React.forwardRef<HTMLTableElement, React.HTMLAttributes<HTMLTableElement>>(({ className, ...props }, ref) => (
  <div data-slot="table-wrapper" className="relative w-full overflow-auto rounded-xl border border-border/70 bg-card">
    <table ref={ref} data-slot="table" className={cn("w-full caption-bottom text-sm", className)} {...props} />
  </div>
));
Table.displayName = "Table";

const TableHeader = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <thead ref={ref} data-slot="table-header" className={cn("[&_tr]:border-b [&_tr]:bg-muted/45", className)} {...props} />
);
TableHeader.displayName = "TableHeader";

const TableBody = React.forwardRef<HTMLTableSectionElement, React.HTMLAttributes<HTMLTableSectionElement>>(
  ({ className, ...props }, ref) => <tbody ref={ref} data-slot="table-body" className={cn("[&_tr:last-child]:border-0", className)} {...props} />
);
TableBody.displayName = "TableBody";

const TableRow = React.forwardRef<HTMLTableRowElement, React.HTMLAttributes<HTMLTableRowElement>>(({ className, ...props }, ref) => (
  <tr
    ref={ref}
    data-slot="table-row"
    className={cn("border-b transition-colors hover:bg-secondary/55 data-[state=selected]:bg-muted/80", className)}
    {...props}
  />
));
TableRow.displayName = "TableRow";

const TableHead = React.forwardRef<HTMLTableCellElement, React.ThHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => (
    <th
      ref={ref}
      data-slot="table-head"
      className={cn("h-11 px-3 text-left align-middle text-xs font-semibold uppercase tracking-wide text-muted-foreground", className)}
      {...props}
    />
  )
);
TableHead.displayName = "TableHead";

const TableCell = React.forwardRef<HTMLTableCellElement, React.TdHTMLAttributes<HTMLTableCellElement>>(
  ({ className, ...props }, ref) => <td ref={ref} data-slot="table-cell" className={cn("p-3 align-middle", className)} {...props} />
);
TableCell.displayName = "TableCell";

export { Table, TableBody, TableCell, TableHead, TableHeader, TableRow };
