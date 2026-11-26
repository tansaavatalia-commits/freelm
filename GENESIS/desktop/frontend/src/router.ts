// Hash routing (#/compiti?stato=failed): works from a plain static server, no history API needed.

export interface Route {
  page: string;
  params: URLSearchParams;
}

export function readRoute(): Route {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [page, query = ""] = raw.split("?");
  return { page: page || "nucleo", params: new URLSearchParams(query) };
}

export function navigate(page: string, params?: Record<string, string>) {
  const query = params && Object.keys(params).length ? `?${new URLSearchParams(params).toString()}` : "";
  window.location.hash = `#/${page}${query}`;
}
