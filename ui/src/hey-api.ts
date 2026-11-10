import type { CreateClientConfig } from "./client/client.gen";
import { apiBase, authToken } from "./lib/connection";

export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  baseUrl: apiBase(),
  auth: authToken,
});
