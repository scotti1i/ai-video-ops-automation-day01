import { Button, Dialog, DialogContent, Field, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Tabs, TabsContent, TabsList, TabsTrigger, Textarea, toast } from "@fifty/workbench-ui";
import { FormEvent, useState } from "react";
import { api, ApiError } from "../api";
import type { Workspace } from "../domain";

export function AccountDialog({ workspace, open, onOpenChange, onCompleted }: { workspace: Workspace; open: boolean; onOpenChange: (open: boolean) => void; onCompleted: () => Promise<void> }) {
  const [mode, setMode] = useState<"account" | "group">("account");
  const [name, setName] = useState("");
  const [handle, setHandle] = useState("");
  const [groupId, setGroupId] = useState(workspace.account_groups[0]?.id ?? "");
  const [platform, setPlatform] = useState("youtube");
  const [context, setContext] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();

  const save = () => mode === "group"
    ? api.createGroup({ name })
    : api.createAccount({ name, handle, group_id: groupId, platform, context });

  const submit = async (event: FormEvent) => {
    event.preventDefault(); setPending(true); setError(undefined);
    try { await save(); await onCompleted(); onOpenChange(false); toast.success(mode === "group" ? "分组已新建" : "账号已新建"); }
    catch (cause) { setError(cause instanceof ApiError ? cause.message : "新建失败，请重试。"); }
    finally { setPending(false); }
  };

  return <Dialog onOpenChange={onOpenChange} open={open}><DialogContent description="账号按业务分组，平台只是账号的一个标签。" title="新增账号或分组"><form className="grid gap-4" onSubmit={(event) => void submit(event)}><Tabs onValueChange={(value) => setMode(value as "account" | "group")} value={mode}><TabsList className="grid w-full grid-cols-2"><TabsTrigger value="account">账号</TabsTrigger><TabsTrigger value="group">分组</TabsTrigger></TabsList><TabsContent value="group"><Field htmlFor="group-name" label="分组名称" required><Input id="group-name" onChange={(event) => setName(event.target.value)} placeholder="例：美区清洁产品" required value={name} /></Field></TabsContent><TabsContent value="account"><div className="grid gap-3"><div className="grid gap-3 sm:grid-cols-2"><Field htmlFor="account-name" label="账号名称" required><Input id="account-name" onChange={(event) => setName(event.target.value)} required value={name} /></Field><Field htmlFor="account-handle" label="@用户名" required><Input id="account-handle" onChange={(event) => setHandle(event.target.value)} placeholder="@brand" required value={handle} /></Field></div><div className="grid gap-3 sm:grid-cols-2"><Field htmlFor="account-group" label="分组" required><Select onValueChange={setGroupId} value={groupId}><SelectTrigger id="account-group"><SelectValue placeholder="选择分组" /></SelectTrigger><SelectContent>{workspace.account_groups.map((group) => <SelectItem key={group.id} value={group.id}>{group.name}</SelectItem>)}</SelectContent></Select></Field><Field htmlFor="account-platform" label="平台" required><Select onValueChange={setPlatform} value={platform}><SelectTrigger id="account-platform"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="youtube">YouTube</SelectItem><SelectItem value="mock-social">示例平台</SelectItem><SelectItem value="tiktok">TikTok · 暂不支持发布</SelectItem></SelectContent></Select></Field></div><Field htmlFor="account-context" label="这个账号的固定风格" hint="只写长期不变的：说话风格、面向人群、不能碰的话题。单条视频的具体要求，写在那条视频里。"><Textarea id="account-context" onChange={(event) => setContext(event.target.value)} value={context} /></Field></div></TabsContent></Tabs>{error ? <p className="m-0 text-sm text-danger" role="alert">{error}</p> : null}<div className="flex justify-end gap-2"><Button onClick={() => onOpenChange(false)} type="button" variant="secondary">取消</Button><Button loading={pending} loadingLabel="保存中" type="submit">保存</Button></div></form></DialogContent></Dialog>;
}

export function ProductDialog({ open, onOpenChange, onCompleted }: { open: boolean; onOpenChange: (open: boolean) => void; onCompleted: () => Promise<void> }) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("");
  const [points, setPoints] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string>();
  const submit = async (event: FormEvent) => { event.preventDefault(); setPending(true); setError(undefined); try { await api.createProduct({ title, description, url: url || null, selling_points: points.split("\n").map((item) => item.trim()).filter(Boolean) }); await onCompleted(); onOpenChange(false); toast.success("商品已新建"); } catch (cause) { setError(cause instanceof ApiError ? cause.message : "新建失败，请重试。"); } finally { setPending(false); } };
  return <Dialog onOpenChange={onOpenChange} open={open}><DialogContent description="先填好商品信息和主要卖点；每条视频主打哪个卖点，做的时候再定。" title="新增商品"><form className="grid gap-4" onSubmit={(event) => void submit(event)}><Field htmlFor="product-title" label="商品名称" required><Input id="product-title" onChange={(event) => setTitle(event.target.value)} required value={title} /></Field><Field htmlFor="product-description" label="商品描述" required><Textarea id="product-description" onChange={(event) => setDescription(event.target.value)} required value={description} /></Field><Field htmlFor="product-url" label="商品链接"><Input id="product-url" onChange={(event) => setUrl(event.target.value)} type="url" value={url} /></Field><Field htmlFor="selling-points" label="卖点" hint="每行写一个，一句话就好。" required><Textarea id="selling-points" onChange={(event) => setPoints(event.target.value)} placeholder={"免工具安装\n30 秒内完成\n适配租房场景"} required value={points} /></Field>{error ? <p className="m-0 text-sm text-danger" role="alert">{error}</p> : null}<div className="flex justify-end gap-2"><Button onClick={() => onOpenChange(false)} type="button" variant="secondary">取消</Button><Button loading={pending} loadingLabel="保存中" type="submit">保存商品</Button></div></form></DialogContent></Dialog>;
}
