export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      ...(options.body && !(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let detail = "Request failed. Check that the backend is running.";
    try {
      const body = await response.json();
      detail =
        typeof body.detail === "string"
          ? body.detail
          : "The request could not be processed.";
    } catch {}
    throw new Error(detail);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export async function streamAnswer(
  path: string,
  body: Record<string, unknown>,
  onEvent: (event: import("./types").AnswerStreamEvent) => void,
): Promise<import("./types").Answer> {
  const response = await fetch("/api" + path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/x-ndjson",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = "Request failed. Check that the backend is running.";
    try {
      const value = await response.json();
      if (typeof value.detail === "string") detail = value.detail;
    } catch {}
    throw new Error(detail);
  }
  if (!response.body) throw new Error("Streaming is unavailable in this browser.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: import("./types").Answer | null = null;
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    const lines = buffer.split("\n");
    buffer = done ? "" : lines.pop() || "";
    for (const line of lines) {
      if (!line.trim()) continue;
      const event = JSON.parse(line) as import("./types").AnswerStreamEvent;
      onEvent(event);
      if (event.type === "error") throw new Error(event.detail);
      if (event.type === "result") result = event.answer;
    }
    if (done) break;
  }
  if (!result) throw new Error("The assistant stream ended before returning an answer.");
  return result;
}
export function uploadRepository(
  file: File,
  onProgress: (progress: number) => void,
): Promise<{ id: string }> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", "/api/repositories/upload");
    request.upload.onprogress = (e) => {
      if (e.lengthComputable)
        onProgress(Math.round((e.loaded / e.total) * 100));
    };
    request.onload = () => {
      try {
        const value = JSON.parse(request.responseText);
        if (request.status >= 200 && request.status < 300) resolve(value);
        else
          reject(
            new Error(
              typeof value.detail === "string" ? value.detail : "Upload failed",
            ),
          );
      } catch {
        reject(new Error("Upload failed. Check the backend connection."));
      }
    };
    request.onerror = () => reject(new Error("Connection lost during upload."));
    const data = new FormData();
    data.append("file", file);
    request.send(data);
  });
}
export function mergeGraph(
  a: import("./types").GraphData,
  b: import("./types").GraphData,
): import("./types").GraphData {
  return {
    nodes: [
      ...new Map([...a.nodes, ...b.nodes].map((n) => [n.id, n])).values(),
    ],
    edges: [
      ...new Map([...a.edges, ...b.edges].map((e) => [e.id, e])).values(),
    ],
    truncated: a.truncated || b.truncated,
  };
}
