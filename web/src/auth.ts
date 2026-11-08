import type { AuthProviderProps } from "react-oidc-context";
import { useAuth } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";

// Authorization Code flow with PKCE against the OIDC provider. No client secret lives in the browser.
export const oidcConfig: AuthProviderProps = {
  authority: import.meta.env.VITE_OIDC_AUTHORITY ?? "http://localhost:8080/realms/fleet",
  client_id: import.meta.env.VITE_OIDC_CLIENT_ID ?? "fleet-web",
  redirect_uri: `${window.location.origin}/`,
  post_logout_redirect_uri: `${window.location.origin}/`,
  scope: "openid profile",
  automaticSilentRenew: true,
  // Session storage: tokens do not outlive the tab.
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),
  onSigninCallback: () => {
    window.history.replaceState({}, document.title, window.location.pathname);
  },
};

/** Roles from the access token, for showing or hiding controls. The API enforces them independently. */
export function rolesFromToken(accessToken: string | undefined): string[] {
  if (!accessToken) return [];
  try {
    const payload = accessToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    const claims = JSON.parse(atob(payload));
    return claims?.realm_access?.roles ?? [];
  } catch {
    return [];
  }
}

export function useRoles() {
  const auth = useAuth();
  const roles = rolesFromToken(auth.user?.access_token);
  return { roles, isEngineer: roles.includes("engineer") };
}
