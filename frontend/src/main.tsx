import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BuildView } from "./BuildView";
import { Home } from "./Home";
import { Monitor } from "./Monitor";
import { navigate, usePath } from "./router";
import "./styles.css";

function App() {
  const path = usePath();
  const build = path.match(/^\/w\/([a-f0-9]{10})$/);
  return (
    <>
      <header className="nav">
        <button className="logo" onClick={() => navigate("/")}>
          <img src="/favicon.svg" alt="" width="26" height="26" />
          FlowMind
        </button>
        <nav>
          <button className={path === "/" ? "on" : ""} onClick={() => navigate("/")}>
            Build
          </button>
          <button className={path === "/monitor" ? "on" : ""} onClick={() => navigate("/monitor")}>
            Live
          </button>
        </nav>
      </header>
      {build ? <BuildView key={build[1]} id={build[1]} /> : path === "/monitor" ? <Monitor /> : <Home />}
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
