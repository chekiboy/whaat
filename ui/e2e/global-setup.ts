import { execFileSync } from "node:child_process";
import { resolve } from "node:path";

export default function globalSetup() {
  execFileSync("uv", ["run", "whaat", "ensure"], {
    cwd: resolve(import.meta.dirname, "../../server"),
    stdio: "inherit",
  });
}
