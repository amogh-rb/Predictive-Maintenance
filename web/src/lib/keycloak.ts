import Keycloak from "keycloak-js";

export const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL,
  realm: import.meta.env.VITE_KEYCLOAK_REALM,
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID,
});

export async function initKeycloak(): Promise<boolean> {
  const authenticated = await keycloak.init({
    onLoad: "login-required",
    pkceMethod: "S256",
    checkLoginIframe: false,
  });
  // Refresh the access token a beat before it expires so a long-open tab
  // (the at-risk list, a live-alerts feed) doesn't suddenly start 401-ing.
  window.setInterval(() => {
    keycloak.updateToken(30).catch(() => keycloak.login());
  }, 20_000);
  return authenticated;
}

export function currentRoles(): string[] {
  return keycloak.tokenParsed?.realm_access?.roles ?? [];
}

export function currentEmail(): string {
  return keycloak.tokenParsed?.email ?? keycloak.tokenParsed?.preferred_username ?? "unknown";
}
