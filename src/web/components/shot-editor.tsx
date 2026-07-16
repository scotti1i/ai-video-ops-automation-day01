import { Button, Field, Input, Select, SelectContent, SelectItem, SelectTrigger, SelectValue, Textarea } from "@fifty/workbench-ui";
import { Plus, Trash2 } from "lucide-react";
import type { StoryboardShot } from "../domain";

export function blankShot(order: number): StoryboardShot {
  return { order, role: "body", duration_seconds: 6, visual: "", voiceover: "", on_screen_text: "" };
}

const SHOT_ROLES = [
  ["hook", "钩子"], ["pain", "痛点"], ["problem", "痛点"], ["feature", "卖点"], ["value", "卖点"], ["proof", "证明"],
  ["objection", "打消顾虑"], ["cta", "引导下单"], ["body", "过渡"],
] as const;

interface Props {
  shots: StoryboardShot[];
  onChange: (shots: StoryboardShot[]) => void;
  title?: string;
  idPrefix?: string;
}

export function ShotEditor({ shots, onChange, title = "镜头清单", idPrefix = "shot" }: Props) {
  const patch = (index: number, key: keyof StoryboardShot, value: string | number) => onChange(shots.map((shot, position) => position === index ? { ...shot, [key]: value } : shot));
  const remove = (index: number) => onChange(shots.filter((_, position) => position !== index).map((shot, position) => ({ ...shot, order: position + 1 })));
  return <div className="grid gap-3"><div className="flex items-center justify-between"><p className="m-0 text-sm font-semibold text-ink">{title}</p><Button className="min-h-11 sm:min-h-8" onClick={() => onChange([...shots, blankShot(shots.length + 1)])} size="sm" type="button" variant="quiet"><Plus className="size-3.5" />加镜头</Button></div>{shots.map((shot, index) => <div className="grid gap-2 rounded-md border border-border bg-surface-muted p-3" key={`${shot.order}-${index}`}><div className="flex items-center justify-between"><span className="text-xs font-semibold text-ink-soft">镜头 {index + 1}</span><Button aria-label={`删除镜头 ${index + 1}`} className="min-h-11 min-w-11 sm:min-h-8 sm:min-w-8" disabled={shots.length === 1} onClick={() => remove(index)} size="sm" type="button" variant="quiet"><Trash2 className="size-3.5" /></Button></div><div className="grid gap-2 sm:grid-cols-[120px_90px_1fr]"><Field htmlFor={`${idPrefix}-role-${index}`} label="作用"><Select onValueChange={(value) => patch(index, "role", value)} value={shot.role || "body"}><SelectTrigger id={`${idPrefix}-role-${index}`}><SelectValue /></SelectTrigger><SelectContent>{SHOT_ROLES.map(([value, label]) => <SelectItem key={value} value={value}>{label}</SelectItem>)}</SelectContent></Select></Field><Field htmlFor={`${idPrefix}-duration-${index}`} label="时长（秒）"><Input id={`${idPrefix}-duration-${index}`} max={120} min={1} onChange={(event) => patch(index, "duration_seconds", Number(event.target.value))} type="number" value={shot.duration_seconds} /></Field><Field htmlFor={`${idPrefix}-visual-${index}`} label="画面" required><Input id={`${idPrefix}-visual-${index}`} onChange={(event) => patch(index, "visual", event.target.value)} required value={shot.visual} /></Field></div><Field htmlFor={`${idPrefix}-voice-${index}`} label="台词"><Textarea className="min-h-20" id={`${idPrefix}-voice-${index}`} onChange={(event) => patch(index, "voiceover", event.target.value)} value={shot.voiceover} /></Field><Field htmlFor={`${idPrefix}-screen-${index}`} label="字幕"><Input id={`${idPrefix}-screen-${index}`} onChange={(event) => patch(index, "on_screen_text", event.target.value)} value={shot.on_screen_text} /></Field></div>)}</div>;
}
