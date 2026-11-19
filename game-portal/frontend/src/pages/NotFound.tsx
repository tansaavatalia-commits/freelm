import { Link } from "react-router";
import { useTitle } from "./useTitle";

export function NotFound() {
  useTitle("Page not found");
  return (
    <section>
      <h1>Page not found</h1>
      <p>
        This page doesn’t exist. <Link to="/">Back to all games</Link>
      </p>
    </section>
  );
}
