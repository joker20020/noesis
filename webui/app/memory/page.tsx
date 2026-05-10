"use client";

import { useState, useEffect, useRef } from "react";

interface GraphNode { id: string; label: string; type: string; group: string; }
interface GraphEdge { from: string; to: string; label: string; }
interface GraphData { nodes: GraphNode[]; edges: GraphEdge[]; }

const colors: Record<string, string> = {
  Service: "#4ade80", Person: "#60a5fa", Config: "#facc15", Error: "#f87171",
  Tool: "#c084fc", Document: "#fb923c", Fact: "#94a3b8", Finding: "#2dd4bf",
  ErrorPattern: "#f87171", ToolPattern: "#c084fc", WebPage: "#38bdf8",
};

export default function MemoryGraphPage() {
  const [data, setData] = useState<GraphData>({ nodes: [], edges: [] });
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const load = (kw = "") => {
    setLoading(true);
    fetch(`http://${process.env.NEXT_PUBLIC_API_HOST || "127.0.0.1"}:${process.env.NEXT_PUBLIC_API_PORT || "8000"}/api/memory/graph?keyword=${encodeURIComponent(kw)}`)
      .then((r) => r.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || data.nodes.length === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = canvas.offsetWidth * 2;
    canvas.height = 500 * 2;
    ctx.scale(2, 2);
    const W = canvas.offsetWidth;
    const H = 500;

    // Layout: circle
    const cx = W / 2, cy = H / 2, r = Math.min(W, H) / 2 - 40;
    const positions: Record<string, { x: number; y: number }> = {};
    data.nodes.forEach((n, i) => {
      const a = (2 * Math.PI * i) / data.nodes.length - Math.PI / 2;
      positions[n.id] = { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) };
    });

    // Draw edges
    ctx.strokeStyle = "#3f3f46";
    ctx.lineWidth = 1;
    data.edges.forEach((e) => {
      const a = positions[e.from], b = positions[e.to];
      if (a && b) {
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
        // Label
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        ctx.fillStyle = "#71717a"; ctx.font = "9px sans-serif";
        ctx.fillText(e.label, mx + 4, my - 4);
      }
    });

    // Draw nodes
    data.nodes.forEach((n) => {
      const p = positions[n.id];
      if (!p) return;
      const color = colors[n.type] || "#94a3b8";
      ctx.fillStyle = color;
      ctx.beginPath(); ctx.arc(p.x, p.y, 8, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = "#18181b"; ctx.lineWidth = 2; ctx.stroke();
      ctx.fillStyle = "#e4e4e7"; ctx.font = "10px sans-serif";
      ctx.fillText(n.label.slice(0, 20), p.x + 12, p.y + 4);
    });

    // Click handler
    const handleClick = (ev: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const mx = ev.clientX - rect.left, my = ev.clientY - rect.top;
      for (const n of data.nodes) {
        const p = positions[n.id];
        if (p && Math.hypot(mx - p.x, my - p.y) < 12) { setSelected(n); return; }
      }
      setSelected(null);
    };
    canvas.addEventListener("click", handleClick);
    return () => canvas.removeEventListener("click", handleClick);
  }, [data]);

  return (
    <div className="max-w-5xl mx-auto p-6 bg-zinc-950 text-zinc-100 min-h-screen">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">Memory Graph</h1>
        <div className="flex gap-2">
          <input
            value={keyword} onChange={(e) => setKeyword(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") load(keyword); }}
            className="bg-zinc-800 rounded px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 w-48"
            placeholder="Search entities..." />
          <button onClick={() => load(keyword)}
            className="text-sm bg-blue-600 hover:bg-blue-700 px-3 py-1.5 rounded transition-colors">Search</button>
          <a href="/" className="text-sm text-zinc-400 hover:text-zinc-200 py-1.5">Chat</a>
        </div>
      </div>

      {loading ? (
        <p className="text-zinc-500">Loading...</p>
      ) : data.nodes.length === 0 ? (
        <p className="text-zinc-500">No entities yet. They are auto-created from agent interactions.</p>
      ) : (
        <>
          <canvas ref={canvasRef} className="w-full border border-zinc-800 rounded-lg bg-zinc-900 mb-4" style={{ height: 500 }} />
          {selected && (
            <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3 text-sm">
              <span className="font-medium">[{selected.type}] {selected.label}</span>
              <span className="text-zinc-500 ml-2">id: {selected.id}</span>
            </div>
          )}
          <div className="flex flex-wrap gap-2 mt-4">
            {Object.entries(colors).map(([type, color]) => (
              <span key={type} className="text-xs px-2 py-0.5 rounded flex items-center gap-1" style={{ color }}>
                <span className="w-2 h-2 rounded-full inline-block" style={{ background: color }} />{type}
              </span>
            ))}
          </div>
          <div className="text-xs text-zinc-600 mt-2">
            {data.nodes.length} entities, {data.edges.length} relationships
          </div>
        </>
      )}
    </div>
  );
}
