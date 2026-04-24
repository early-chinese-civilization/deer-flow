export type CallbackErrorCopy = {
  title: string;
  description: string;
};

export function normalizeCallbackError(
  value: string | string[] | undefined,
): string | null {
  const rawValue = Array.isArray(value) ? value[0] : value;
  return rawValue?.trim() ? rawValue : null;
}

export function getCallbackErrorCopy(error: string): CallbackErrorCopy {
  switch (error) {
    case "token_exchange_failed":
      return {
        title: "Sign-in could not be completed",
        description:
          "The identity provider rejected the callback exchange. Please retry after checking the login configuration.",
      };
    case "callback_upstream_failed":
      return {
        title: "The identity provider could not be reached",
        description:
          "DeerFlow received the callback request, but the upstream auth request failed before the session could be created.",
      };
    case "token_not_yet_valid":
      return {
        title: "The returned token is not valid yet",
        description:
          "The identity provider issued a token whose start time is later than the DeerFlow backend clock. Align the backend and identity-provider system time, then retry.",
      };
    case "token_validation_failed":
      return {
        title: "The returned token could not be verified",
        description:
          "DeerFlow received a token from the identity provider, but it failed local JWT validation before the session could be created.",
      };
    case "token_verification_unavailable":
      return {
        title: "Token verification is temporarily unavailable",
        description:
          "DeerFlow could not complete JWT verification during the callback. Retry after the backend regains access to the identity-provider signing keys.",
      };
    case "user_sync_failed":
      return {
        title: "Sign-in succeeded, but DeerFlow could not finish account setup",
        description:
          "The callback completed with the identity provider, but DeerFlow failed while syncing the local user record. Check backend logs for the consumer callback failure.",
      };
    case "callback_failed":
      return {
        title: "Sign-in is temporarily unavailable",
        description:
          "DeerFlow received the callback, but the session could not be established for an uncategorized reason. Check backend logs for the exact callback exception.",
      };
    case "csrf_mismatch":
    case "missing_pkce":
    case "missing_state":
    case "invalid_state":
    case "missing_code":
      return {
        title: "The login flow expired",
        description:
          "The browser returned from the identity provider without the expected callback state. Start a fresh sign-in flow in this tab.",
      };
    default:
      return {
        title: "Sign-in failed",
        description:
          "DeerFlow could not complete the login callback. Start a fresh sign-in flow when you are ready.",
      };
  }
}
