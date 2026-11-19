import { Route, Routes } from "react-router";
import { Layout } from "./components/Layout";
import { Category } from "./pages/Category";
import { Home } from "./pages/Home";
import { About, Advertise, Privacy, Terms } from "./pages/Info";
import { Favorites, History } from "./pages/Lists";
import { NotFound } from "./pages/NotFound";
import { Play } from "./pages/Play";
import { Search } from "./pages/Search";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="c/:category" element={<Category />} />
        <Route path="search" element={<Search />} />
        <Route path="play/:slug" element={<Play />} />
        <Route path="favorites" element={<Favorites />} />
        <Route path="history" element={<History />} />
        <Route path="about" element={<About />} />
        <Route path="privacy" element={<Privacy />} />
        <Route path="terms" element={<Terms />} />
        <Route path="advertise" element={<Advertise />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
