import { NavLink, Route, Routes, useLocation } from "react-router-dom"
import { Library } from "./pages/Library"
import { LivePage } from "./pages/Live"
import { Planner } from "./pages/Planner"
import { SessionPage } from "./pages/Session"
import { SetupsIndex, SetupsPage } from "./pages/Setups"

export function App() {
  if (useLocation().pathname.startsWith("/live")) return <LivePage />
  return (
    <div className="shell">
      <header className="topbar">
        <span className="brand">
          Tele<b>metria</b>
        </span>
        <nav className="topnav">
          <NavLink to="/" end>
            Library
          </NavLink>
          <NavLink to="/planner">Planner</NavLink>
          <NavLink to="/setups">Setups</NavLink>
          <NavLink to="/live">Live</NavLink>
        </nav>
      </header>
      <main className="page">
        <Routes>
          <Route path="/" element={<Library />} />
          <Route path="/session/:id/:tab?" element={<SessionPage />} />
          <Route path="/planner" element={<Planner />} />
          <Route path="/setups" element={<SetupsIndex />} />
          <Route path="/track/:track/setups" element={<SetupsPage />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </div>
  )
}
