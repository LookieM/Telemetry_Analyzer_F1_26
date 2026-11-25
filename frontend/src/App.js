import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import { Library } from "./pages/Library";
import { LivePage } from "./pages/Live";
import { Planner } from "./pages/Planner";
import { SessionPage } from "./pages/Session";
import { SetupsIndex, SetupsPage } from "./pages/Setups";
export function App() {
    if (useLocation().pathname.startsWith("/live"))
        return _jsx(LivePage, {});
    return (_jsxs("div", { className: "shell", children: [_jsxs("header", { className: "topbar", children: [_jsxs("span", { className: "brand", children: ["Tele", _jsx("b", { children: "metria" })] }), _jsxs("nav", { className: "topnav", children: [_jsx(NavLink, { to: "/", end: true, children: "Library" }), _jsx(NavLink, { to: "/planner", children: "Planner" }), _jsx(NavLink, { to: "/setups", children: "Setups" }), _jsx(NavLink, { to: "/live", children: "Live" })] })] }), _jsx("main", { className: "page", children: _jsxs(Routes, { children: [_jsx(Route, { path: "/", element: _jsx(Library, {}) }), _jsx(Route, { path: "/session/:id/:tab?", element: _jsx(SessionPage, {}) }), _jsx(Route, { path: "/planner", element: _jsx(Planner, {}) }), _jsx(Route, { path: "/setups", element: _jsx(SetupsIndex, {}) }), _jsx(Route, { path: "/track/:track/setups", element: _jsx(SetupsPage, {}) }), _jsx(Route, { path: "*", element: _jsx("p", { children: "Page not found." }) })] }) })] }));
}
