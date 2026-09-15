"use client";
import { useEffect, useRef, useState } from "react";
import cytoscape, { Core, LayoutOptions } from "cytoscape";
import dagre from "cytoscape-dagre";
cytoscape.use(dagre);
import { Plus, Minus, Maximize, Focus } from "lucide-react";
import type { GraphData, Node } from "@/lib/types";
export const colors: Record<string, string> = {
  Component: "#b3a0f5",
  File: "#7f91ac",
  Class: "#caa0ff",
  Interface: "#e6b6f7",
  Function: "#61c9bf",
  Method: "#69a8e8",
  Endpoint: "#e4b85f",
  DatabaseEntity: "#e99091",
  ExternalPackage: "#9dada9",
  UnresolvedSymbol: "#666979",
};
export default function Graph({
  data,
  onSelect,
  selected,
  highlights,
  layout = "cose",
}: {
  data: GraphData;
  onSelect: (n: Node) => void;
  selected?: string;
  highlights: string[];
  layout?: string;
}) {
  const container = useRef<HTMLDivElement>(null);
  const cy = useRef<Core | null>(null);
  const selectRef = useRef(onSelect);
  const [hover, setHover] = useState<Node | null>(null);
  useEffect(() => {
    selectRef.current = onSelect;
  }, [onSelect]);
  useEffect(() => {
    if (!container.current) return;
    const instance = cytoscape({
      container: container.current,
      elements: [],
      minZoom: 0.15,
      maxZoom: 1.6,
      wheelSensitivity: 0.18,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            "border-color": "data(color)",
            "border-width": 1,
            "background-opacity": 0.14,
            label: "data(label)",
            color: "#d9dee9",
            "font-family": "ui-monospace, SFMono-Regular, monospace",
            "font-size": 11,
            "text-wrap": "wrap",
            "text-max-width": "108px",
            "text-valign": "center",
            "text-margin-y": 0,
            width: 122,
            height: 40,
            shape: "round-rectangle",
          },
        },
        {
          selector: 'node[type="Component"]',
          style: {
            width: 138,
            height: 66,
            "font-size": 12,
            "border-width": 1.5,
          },
        },
        {
          selector: 'node[type="Endpoint"]',
          style: { shape: "round-rectangle", "border-width": 1.5 },
        },
        { selector: 'node[type="DatabaseEntity"]', style: { shape: "barrel" } },
        {
          selector: "edge",
          style: {
            width: 1,
            "line-color": "#3d4356",
            "target-arrow-color": "#4d556c",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            "arrow-scale": 0.8,
            opacity: 0.75,
          },
        },
        {
          selector: 'edge[resolution="unresolved"]',
          style: { "line-style": "dashed", opacity: 0.35 },
        },
        { selector: ".dim", style: { opacity: 0.12 } },
        {
          selector: "node.highlight",
          style: {
            "border-width": 3,
            "background-opacity": 0.5,
            color: "#fff",
          },
        },
        {
          selector: "edge.highlight",
          style: {
            "line-color": "#b5a0ff",
            "target-arrow-color": "#b5a0ff",
            width: 2,
            opacity: 1,
          },
        },
        {
          selector: "node:selected",
          style: {
            "border-width": 3,
            "border-color": "#fff",
            "background-opacity": 0.4,
          },
        },
      ],
    });
    cy.current = instance;
    instance.on("tap", "node", (e) =>
      selectRef.current(e.target.data() as Node),
    );
    instance.on("mouseover", "node", (e) => {
      setHover(e.target.data());
      container.current!.style.cursor = "pointer";
    });
    instance.on("mouseout", "node", () => {
      setHover(null);
      if (container.current) container.current.style.cursor = "default";
    });
    return () => {
      instance.destroy();
      cy.current = null;
    };
  }, []);
  useEffect(() => {
    const instance = cy.current;
    if (!instance) return;
    instance.elements().remove();
    instance.add([
      ...data.nodes.map((n) => ({
        data: {
          ...n,
          label:
            n.type === "Component" ? `${n.name}\n${n.count} symbols` : n.name,
          color: colors[n.type] || "#8e9bb4",
        },
      })),
      ...data.edges.map((e) => ({ data: e })),
    ]);
    instance
      .layout({
        name: layout,
        animate: false,
        fit: true,
        padding: 65,
        ...(layout === "cose"
          ? {
              nodeRepulsion: 50000,
              idealEdgeLength: 150,
              gravity: 0.15,
              nodeDimensionsIncludeLabels: true,
            }
          : {}),
        ...(layout === "dagre"
          ? {
              rankDir: "TB",
              nodeSep: 25,
              rankSep: 60,
              edgeSep: 10,
              nodeDimensionsIncludeLabels: true,
            }
          : {}),
      } as LayoutOptions)
      .run();
    const observer = new ResizeObserver(() => instance.resize());
    if (container.current) observer.observe(container.current);
    return () => observer.disconnect();
  }, [data, layout]);
  useEffect(() => {
    const instance = cy.current;
    if (!instance) return;
    instance.elements().removeClass("dim highlight").unselect();
    const ids = highlights.length ? highlights : selected ? [selected] : [];
    if (ids.length) {
      const nodes = instance.nodes().filter((n) => ids.includes(n.id()));
      if (nodes.length) {
        const visible = highlights.length
          ? nodes.union(
              instance
                .edges()
                .filter(
                  (e) =>
                    ids.includes(e.source().id()) &&
                    ids.includes(e.target().id()),
                ),
            )
          : nodes.closedNeighborhood();
        instance.elements().addClass("dim");
        visible.removeClass("dim").addClass("highlight");
      }
    }
    if (selected) instance.getElementById(selected).select();
  }, [selected, highlights, data]);
  return (
    <div className="graph-canvas">
      <div
        ref={container}
        className="cy-container"
        aria-label="Interactive repository dependency graph"
      />
      <div className="graph-watermark">
        REPOGRAPH /{" "}
        {data.nodes.some((n) => n.type === "Component")
          ? "ARCHITECTURE"
          : "DEPENDENCIES"}
      </div>
      {hover && (
        <div className="graph-tooltip">
          <strong>{hover.name}</strong>
          <span>
            {hover.type}{" "}
            {hover.file_path ? `· ${hover.file_path}:${hover.start_line}` : ""}
          </span>
          <small>
            Click to inspect{" "}
            {hover.type === "Component" ? "and drill into this component" : ""}
          </small>
        </div>
      )}
      <div className="graph-zoom">
        <button
          title="Zoom in"
          onClick={() => cy.current?.zoom((cy.current?.zoom() || 1) * 1.2)}
        >
          <Plus size={17} />
        </button>
        <button
          title="Zoom out"
          onClick={() => cy.current?.zoom((cy.current?.zoom() || 1) / 1.2)}
        >
          <Minus size={17} />
        </button>
        <button
          title="Fit graph"
          onClick={() => cy.current?.fit(undefined, 60)}
        >
          <Maximize size={17} />
        </button>
        <button
          title="Focus selected node"
          onClick={() => {
            const node = cy.current?.getElementById(selected || "");
            if (node?.length)
              cy.current?.animate({
                fit: { eles: node.closedNeighborhood(), padding: 80 },
                duration: 300,
              });
          }}
        >
          <Focus size={17} />
        </button>
      </div>
      <div className="graph-legend">
        {[...new Set(data.nodes.map((n) => n.type))].map((type) => (
          <span key={type}>
            <i style={{ background: colors[type] || "#9aa" }} />
            {type === "DatabaseEntity"
              ? "Database"
              : type === "ExternalPackage"
                ? "Package"
                : type}
          </span>
        ))}
      </div>
      {data.nodes.length === 0 && (
        <div className="graph-empty">No nodes match these filters.</div>
      )}
    </div>
  );
}
