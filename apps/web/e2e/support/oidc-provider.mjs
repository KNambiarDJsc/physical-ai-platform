// A real OpenID Connect provider for the sign-in tests (AUTH-002): panva/oidc-provider, a certified OpenID
// Provider implementation, run locally with its built-in development login and consent pages (any login and
// password are accepted). Test use only: never part of the product or its images.
//
//   node e2e/support/oidc-provider.mjs --port 9411 --web-origin http://127.0.0.1:3765 \
//        --audience https://api.pap.test --stop-file ../../var/smoke/dev-stack/oidc-stop
//
// Issues RS256-signed JWT access tokens for the API audience (resource indicators, RFC 8707), so the API validates
// them exactly as it would tokens from Keycloak or any other provider.
import { existsSync, unlinkSync } from "node:fs";
import { parseArgs } from "node:util";
import { exportJWK, generateKeyPair } from "jose";
import Provider from "oidc-provider";

const { values: a } = parseArgs({
  options: {
    port: { type: "string", default: "9411" },
    "web-origin": { type: "string" },
    audience: { type: "string", default: "https://api.pap.test" },
    "stop-file": { type: "string" },
  },
});
if (!a["web-origin"]) throw new Error("--web-origin is required");
const issuer = `http://127.0.0.1:${a.port}`;

const { privateKey } = await generateKeyPair("RS256", { extractable: true });
const jwk = { ...(await exportJWK(privateKey)), kid: "test-rs256", alg: "RS256", use: "sig" };

const provider = new Provider(issuer, {
  clients: [
    {
      client_id: "pap-web",
      token_endpoint_auth_method: "none", // public client: PKCE is what protects the code
      redirect_uris: [`${a["web-origin"]}/auth/callback`],
      grant_types: ["authorization_code"],
      response_types: ["code"],
    },
  ],
  pkce: { required: () => true },
  jwks: { keys: [jwk] },
  cookies: { keys: ["test-only-cookie-signing-key"] },
  claims: { openid: ["sub"], profile: ["name", "preferred_username"], email: ["email"] },
  findAccount: async (_ctx, id) => ({
    accountId: id,
    claims: async () => ({ sub: id, name: `Test user ${id}`, preferred_username: id, email: `${id}@example.test` }),
  }),
  features: {
    devInteractions: { enabled: true },
    resourceIndicators: {
      enabled: true,
      defaultResource: () => a.audience,
      useGrantedResource: () => true,
      getResourceServerInfo: (_ctx, resource) => {
        if (resource !== a.audience) throw new Error(`unknown resource ${resource}`);
        return { scope: "api", audience: resource, accessTokenTTL: 600, accessTokenFormat: "jwt", jwt: { sign: { alg: "RS256" } } };
      },
    },
  },
  ttl: { AccessToken: 600, AuthorizationCode: 60, IdToken: 600, Grant: 600, Interaction: 600, Session: 600 },
});
provider.proxy = false;

const server = provider.listen(Number(a.port), "127.0.0.1", () => {
  console.log(JSON.stringify({ issuer, audience: a.audience, client_id: "pap-web" }));
});

if (a["stop-file"]) {
  if (existsSync(a["stop-file"])) unlinkSync(a["stop-file"]);
  setInterval(() => {
    if (existsSync(a["stop-file"])) {
      server.close();
      process.exit(0);
    }
  }, 500).unref();
}
