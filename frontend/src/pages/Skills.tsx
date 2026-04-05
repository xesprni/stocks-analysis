import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Plus,
  Trash2,
  Edit,
  RefreshCw,
  Wrench,
  FileText,
} from "lucide-react";

import { api, type SkillView, type SkillDetailView } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useNotifier } from "@/components/ui/notifier";

export function SkillsPage() {
  const queryClient = useQueryClient();
  const notifier = useNotifier();

  const [skills, setSkills] = useState<SkillView[]>([]);
  const [loading, setLoading] = useState(true);
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [previewDialogOpen, setPreviewDialogOpen] = useState(false);
  const [selectedSkill, setSelectedSkill] = useState<SkillDetailView | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const [createForm, setCreateForm] = useState({
    name: "",
    description: "",
    content: "",
  });
  const [editForm, setEditForm] = useState({
    name: "",
    description: "",
    content: "",
  });

  const fetchSkills = async () => {
    try {
      setLoading(true);
      const data = await api.listSkills();
      setSkills(data);
    } catch (err) {
      notifier.error("加载 Skills 失败", err instanceof Error ? err.message : "");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSkills();
  }, []);

  const handleReload = async () => {
    try {
      const result = await api.reloadSkills();
      await fetchSkills();
      notifier.success("Skills 已重新加载", `共 ${result.count} 个 skill`);
    } catch (err) {
      notifier.error("重新加载失败", err instanceof Error ? err.message : "");
    }
  };

  const handleCreate = async () => {
    if (!createForm.name || !createForm.description) {
      notifier.error("验证错误", "名称和描述为必填项");
      return;
    }
    try {
      setSubmitting(true);
      await api.createSkill({
        name: createForm.name,
        description: createForm.description,
        content: createForm.content,
      });
      notifier.success("Skill 已创建", createForm.name);
      setCreateDialogOpen(false);
      setCreateForm({ name: "", description: "", content: "" });
      fetchSkills();
    } catch (err) {
      notifier.error("创建 Skill 失败", err instanceof Error ? err.message : "");
    } finally {
      setSubmitting(false);
    }
  };

  const openEditDialog = async (skill: SkillView) => {
    try {
      const detail = await api.getSkill(skill.name);
      setEditForm({
        name: detail.name,
        description: detail.description,
        content: detail.content,
      });
      setEditDialogOpen(true);
    } catch (err) {
      notifier.error("加载 Skill 详情失败", err instanceof Error ? err.message : "");
    }
  };

  const handleUpdate = async () => {
    if (!editForm.name) return;
    try {
      setSubmitting(true);
      await api.updateSkill(editForm.name, {
        description: editForm.description,
        content: editForm.content,
      });
      notifier.success("Skill 已更新", editForm.name);
      setEditDialogOpen(false);
      fetchSkills();
    } catch (err) {
      notifier.error("更新 Skill 失败", err instanceof Error ? err.message : "");
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (name: string) => {
    if (!window.confirm(`确认删除 Skill "${name}"？此操作不可撤销。`)) return;
    try {
      await api.deleteSkill(name);
      notifier.success("Skill 已删除", name);
      fetchSkills();
    } catch (err) {
      notifier.error("删除 Skill 失败", err instanceof Error ? err.message : "");
    }
  };

  const openPreview = async (skill: SkillView) => {
    try {
      const detail = await api.getSkill(skill.name);
      setSelectedSkill(detail);
      setPreviewDialogOpen(true);
    } catch (err) {
      notifier.error("加载 Skill 详情失败", err instanceof Error ? err.message : "");
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <Wrench className="h-5 w-5" />
              Skills 管理
            </CardTitle>
            <CardDescription className="mt-1">
              管理 Agent 可用的 Skill 定义。每个 Skill 由 SKILL.md 文件定义，包含名称、描述和指令内容。
            </CardDescription>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={handleReload}>
              <RefreshCw className="mr-2 h-4 w-4" />
              刷新
            </Button>
            <Button size="sm" onClick={() => setCreateDialogOpen(true)}>
              <Plus className="mr-2 h-4 w-4" />
              新建 Skill
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : skills.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Wrench className="mb-4 h-12 w-12 opacity-50" />
              <p>暂无 Skill</p>
              <p className="text-sm">点击「新建 Skill」创建第一个 Skill。</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {skills.map((skill) => (
                <Card key={skill.name} className="group relative border-border/80 transition-shadow hover:shadow-md">
                  <CardHeader className="pb-3">
                    <div className="flex items-start justify-between">
                      <CardTitle className="text-base">{skill.name}</CardTitle>
                      <Badge variant="secondary" className="shrink-0">
                        <FileText className="mr-1 h-3 w-3" />
                        SKILL.md
                      </Badge>
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="mb-4 line-clamp-2 text-sm text-muted-foreground">
                      {skill.description}
                    </p>
                    <div className="flex justify-end gap-2">
                      <Button variant="ghost" size="sm" onClick={() => openPreview(skill)}>
                        <FileText className="h-4 w-4" />
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => openEditDialog(skill)}>
                        <Edit className="h-4 w-4" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        className="text-destructive"
                        onClick={() => handleDelete(skill.name)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Create Skill Dialog */}
      <Dialog open={createDialogOpen} onOpenChange={setCreateDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>新建 Skill</DialogTitle>
            <DialogDescription>创建一个新的 Agent Skill 定义。</DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="skill-name">名称</Label>
              <Input
                id="skill-name"
                placeholder="e.g. my-analysis-skill"
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                仅支持字母、数字、连字符和下划线。
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-desc">描述</Label>
              <Input
                id="skill-desc"
                placeholder="Skill 的简短描述"
                value={createForm.description}
                onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="skill-content">内容 (Markdown)</Label>
              <Textarea
                id="skill-content"
                placeholder="Skill 的 Markdown 指令内容..."
                rows={12}
                value={createForm.content}
                onChange={(e) => setCreateForm({ ...createForm, content: e.target.value })}
                className="font-mono text-sm"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleCreate} disabled={submitting || !createForm.name || !createForm.description}>
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              创建
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Edit Skill Dialog */}
      <Dialog open={editDialogOpen} onOpenChange={setEditDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>编辑 Skill</DialogTitle>
            <DialogDescription>
              修改 Skill「{editForm.name}」的描述和内容。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-skill-desc">描述</Label>
              <Input
                id="edit-skill-desc"
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="edit-skill-content">内容 (Markdown)</Label>
              <Textarea
                id="edit-skill-content"
                rows={14}
                value={editForm.content}
                onChange={(e) => setEditForm({ ...editForm, content: e.target.value })}
                className="font-mono text-sm"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditDialogOpen(false)}>
              取消
            </Button>
            <Button onClick={handleUpdate} disabled={submitting}>
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Preview Skill Dialog */}
      <Dialog open={previewDialogOpen} onOpenChange={setPreviewDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>{selectedSkill?.name}</DialogTitle>
            <DialogDescription>{selectedSkill?.description}</DialogDescription>
          </DialogHeader>
          <div className="max-h-[60vh] overflow-auto rounded-md border bg-muted/30 p-4">
            <pre className="whitespace-pre-wrap font-mono text-sm">
              {selectedSkill?.content || "（无内容）"}
            </pre>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setPreviewDialogOpen(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default SkillsPage;
