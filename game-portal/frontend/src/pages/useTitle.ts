import { useEffect } from "react";

export function useTitle(title: string, description?: string) {
  useEffect(() => {
    document.title = title ? `${title} — Tabluo` : "Tabluo — Classic games, calmly done";
    if (description) document.querySelector('meta[name="description"]')?.setAttribute("content", description);
  }, [title, description]);
}
