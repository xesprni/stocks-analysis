import type { ReportDetail, ReportSummary } from "@/api/client";
import { MarkdownViewer } from "@/components/MarkdownViewer";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";

type Props = {
  reports: ReportSummary[];
  selectedRunId: string;
  detail: ReportDetail | null;
  onSelect: (runId: string) => void;
};

export function ReportsPage({ reports, selectedRunId, detail, onSelect }: Props) {
  return (
    <div className="grid gap-6 lg:grid-cols-5">
      <Card className="lg:col-span-2">
        <CardHeader>
          <CardTitle>报告列表</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run ID</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead>Model</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {reports.map((item) => (
                <TableRow
                  key={item.run_id}
                  className="cursor-pointer"
                  data-state={item.run_id === selectedRunId ? "selected" : undefined}
                  onClick={() => onSelect(item.run_id)}
                >
                  <TableCell className="font-mono text-xs">{item.run_id}</TableCell>
                  <TableCell>{item.provider_id || "-"}</TableCell>
                  <TableCell>{item.model || "-"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card className="lg:col-span-3">
        <CardHeader>
          <CardTitle>报告内容</CardTitle>
        </CardHeader>
        <CardContent>
          {!detail ? (
            <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">暂无</div>
          ) : (
            <Tabs defaultValue="markdown">
              <TabsList>
                <TabsTrigger value="markdown">Markdown</TabsTrigger>
                <TabsTrigger value="json">Raw JSON</TabsTrigger>
              </TabsList>
              <TabsContent value="markdown">
                <MarkdownViewer markdown={detail.report_markdown} />
              </TabsContent>
              <TabsContent value="json">
                <pre>{JSON.stringify(detail.raw_data, null, 2)}</pre>
              </TabsContent>
            </Tabs>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
