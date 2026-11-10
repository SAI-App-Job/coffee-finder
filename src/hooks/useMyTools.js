import { useCallback, useEffect, useState } from "react";

const STORAGE_KEY = "coffee-finder:my-tools";

// 登録できる道具の種類。順番は、設定画面の表示順
export const TOOL_KINDS = [
  { id: "dripper", label: "ドリッパー", example: "例: HARIO V60 02 透過ドリッパー" },
  { id: "paper", label: "ペーパー", example: "例: HARIO V60用ペーパーフィルター 02" },
  { id: "grinder", label: "コーヒーミル", example: "例: タイムモア C3、コマンダンテ C40" },
];
const KIND_IDS = TOOL_KINDS.map((k) => k.id);

function generateId() {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

const text = (v, max) => (typeof v === "string" ? v.trim().slice(0, max) : "");

// 保存された値を、扱える形に整える(壊れた値・知らない種類は捨てる)
function normalize(raw) {
  if (!raw || typeof raw !== "object" || !KIND_IDS.includes(raw.kind)) return null;
  const name = text(raw.name, 80);
  if (!name) return null;
  return {
    id: typeof raw.id === "string" && raw.id ? raw.id : generateId(),
    kind: raw.kind,
    name,
    maker: text(raw.maker, 60),
    gtin: text(raw.gtin, 14),
    url: text(raw.url, 500),
    note: text(raw.note, 300),
    createdAt: typeof raw.createdAt === "string" ? raw.createdAt : new Date().toISOString(),
  };
}

function loadTools() {
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.map(normalize).filter(Boolean) : [];
  } catch {
    return [];
  }
}

// 「マイツール」: 自分の道具(ドリッパー・ペーパー・コーヒーミル)の登録。端末内(localStorage)に保存する。
// テイスティングログの「抽出方法」「挽き目」を、ここから選んで書けるようにするためのもの。
export function useMyTools() {
  const [tools, setTools] = useState(loadTools);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(tools));
    } catch {
      // プライベートブラウジング等でlocalStorageが使えない場合は保存をスキップ
    }
  }, [tools]);

  const addTool = useCallback((input) => {
    const tool = normalize({ ...input, id: generateId(), createdAt: new Date().toISOString() });
    if (tool) setTools((prev) => [...prev, tool]);
  }, []);

  const updateTool = useCallback((id, input) => {
    setTools((prev) =>
      prev.map((tool) => (tool.id === id ? (normalize({ ...tool, ...input, id, kind: tool.kind }) ?? tool) : tool))
    );
  }, []);

  const deleteTool = useCallback((id) => {
    setTools((prev) => prev.filter((tool) => tool.id !== id));
  }, []);

  return { tools, addTool, updateTool, deleteTool };
}
