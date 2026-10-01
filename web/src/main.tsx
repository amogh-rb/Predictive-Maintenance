import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import App from "./App";
import { initKeycloak } from "./lib/keycloak";

const root = createRoot(document.getElementById("root")!);

initKeycloak()
  .then((authenticated) => {
    if (!authenticated) {
      // login-required should have redirected before this resolves; this
      // branch only fires if Keycloak itself is unreachable.
      root.render(<p style={{ padding: 24 }}>Could not reach Keycloak. Is the stack up?</p>);
      return;
    }
    root.render(
      <StrictMode>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </StrictMode>,
    );
  })
  .catch((err) => {
    root.render(<p style={{ padding: 24 }}>Keycloak init failed: {String(err)}</p>);
  });
