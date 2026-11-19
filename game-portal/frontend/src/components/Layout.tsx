import { useEffect } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router";

export function Layout() {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return (
    <>
      <a className="skip" href="#main">Skip to content</a>
      <header className="site-header">
        <Link to="/" className="logo" aria-label="Tabluo home">
          <span className="logo-mark" aria-hidden="true" />
          Tabluo
        </Link>
        <nav aria-label="Main">
          <NavLink to="/" end>Games</NavLink>
          <NavLink to="/play/nonogram">Daily</NavLink>
          <NavLink to="/favorites">Favorites</NavLink>
        </nav>
        <form
          role="search"
          className="search"
          onSubmit={(e) => {
            e.preventDefault();
            const q = new FormData(e.currentTarget).get("q");
            navigate(`/search?q=${encodeURIComponent(String(q ?? ""))}`);
          }}
        >
          <label className="sr-only" htmlFor="q">Search games</label>
          <input id="q" name="q" type="search" placeholder="Search games" autoComplete="off" />
        </form>
      </header>
      <main id="main">
        <Outlet />
      </main>
      <footer className="site-footer">
        <nav aria-label="Footer">
          <Link to="/about">About</Link>
          <Link to="/history">Recently played</Link>
          <Link to="/advertise">Advertise</Link>
          <Link to="/privacy">Privacy</Link>
          <Link to="/terms">Terms</Link>
        </nav>
        <p>© {new Date().getFullYear()} Tabluo. Original games, no tracking cookies.</p>
      </footer>
    </>
  );
}
