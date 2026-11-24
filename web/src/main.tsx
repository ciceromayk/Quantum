import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import Falha from "./Falha";
import "./estilo.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Falha>
      <App />
    </Falha>
  </StrictMode>,
);
