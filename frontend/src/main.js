import { jsx as _jsx } from "react/jsx-runtime";
import "@fontsource/jetbrains-mono/latin-400.css";
import "@fontsource/jetbrains-mono/latin-600.css";
import "@fontsource/jetbrains-mono/latin-700.css";
import "@fontsource/titillium-web/latin-400.css";
import "@fontsource/titillium-web/latin-600.css";
import "@fontsource/titillium-web/latin-700.css";
import "@fontsource/titillium-web/latin-700-italic.css";
import "@fontsource/titillium-web/latin-900.css";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./styles/tokens.css";
import "./styles/app.css";
const queryClient = new QueryClient({
    defaultOptions: { queries: { staleTime: 60_000, refetchOnWindowFocus: false, retry: false } },
});
function render() {
    ReactDOM.createRoot(document.getElementById("root")).render(_jsx(React.StrictMode, { children: _jsx(QueryClientProvider, { client: queryClient, children: _jsx(BrowserRouter, { future: { v7_startTransition: true, v7_relativeSplatPath: true }, children: _jsx(App, {}) }) }) }));
}
// Canvas charts read the font once when they draw: wait for the bundled fonts (local, so this is quick).
Promise.all(["400 13px 'Titillium Web'", "700 13px 'Titillium Web'", "400 13px 'JetBrains Mono'"].map((f) => document.fonts.load(f)))
    .catch(() => undefined)
    .finally(render);
