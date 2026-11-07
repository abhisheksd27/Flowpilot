// Build: npm install && npm run build (from ui_assets).
import mermaid from "mermaid";

mermaid.initialize({
  startOnLoad: false,
  securityLevel: "strict",
  theme: "base",
  flowchart: { htmlLabels: false, useMaxWidth: true },
  themeVariables: { fontFamily: "Arial, sans-serif", fontSize: "14px" },
});

const instances = new WeakMap();
let nextId = 0;

function updateNodes(state) {
  if (!state.svg) return;
  const { statuses, nodeIds } = state.latest;
  const byId = {};
  for (const [name, id] of Object.entries(nodeIds)) {
    const status = statuses[name] || "pending";
    byId[id] = status;
    const node = state.nodes.get(id);
    if (!node) continue;
    const visual = name === "diagnose_and_fix" && status === "running"
      ? "repairing" : status;
    if (node.dataset.status !== visual) node.dataset.status = visual;
    node.setAttribute("aria-label", `${node.textContent.trim()}: ${visual}`);
  }
  for (const path of state.edges) {
    const match = /^L_([A-Z]+)_([A-Z]+)_\d+$/.exec(path.id);
    if (!match) continue;
    const [, source, target] = match;
    const isFailureRoute = target === "FIX" && ["EXEC", "VALIDATE"].includes(source);
    const active = byId[target] === "running" && (
      isFailureRoute ? byId[source] === "failed"
        : ["running", "success"].includes(byId[source])
    );
    path.classList.toggle("flow-active", active);
    path.classList.toggle("flow-repair", active && (source === "FIX" || target === "FIX"));
  }
  state.host.dataset.updateCount = String(Number(state.host.dataset.updateCount || 0) + 1);
}

export default function ({ parentElement, data }) {
  let state = instances.get(parentElement);
  if (!state) {
    const host = parentElement.querySelector(".flow-viewport");
    state = { host, latest: data, svg: null, nodes: new Map(), edges: [] };
    instances.set(parentElement, state);
    host.dataset.renderCount = "0";

    // Layout is computed ONCE per mount, never for a status event.
    mermaid.render(`flowpilot-${++nextId}`, data.diagram).then(({ svg }) => {
      if (!host.isConnected) return;
      host.innerHTML = svg; // Mermaid's strict renderer sanitizes the trusted diagram.
      state.svg = host.querySelector("svg");
      state.svg.setAttribute("role", "img");
      state.svg.setAttribute("aria-label", "Live self-healing pipeline architecture");
      for (const node of state.svg.querySelectorAll("g.node")) {
        const match = /^flowchart-(.+)-\d+$/.exec(node.id);
        if (match) state.nodes.set(match[1], node);
        node.dataset.status = "pending";
      }
      state.edges = [...state.svg.querySelectorAll("path[id^='L_']")];
      host.dataset.renderCount = "1";
      // Paint the initial layout before transitioning to the latest state.
      requestAnimationFrame(() => requestAnimationFrame(() => updateNodes(state)));
    }).catch((error) => {
      host.textContent = `Unable to render the architecture: ${error.message}`;
      host.setAttribute("role", "alert");
    });
  }
  state.latest = data;
  updateNodes(state);
}
