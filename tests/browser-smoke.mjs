// Optional integration check in a disposable Chromium profile; no real browsing.
import assert from "node:assert/strict";
import { spawn, spawnSync, execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, readFileSync, readdirSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const root = fileURLToPath(new URL("../", import.meta.url));
if (process.env.PACKAGE_ROOT && !process.env.PACKAGE_NAMESPACE) {
  const packageRoot = process.env.PACKAGE_ROOT;
  const args = ["--ro-bind", "/", "/", "--dev-bind", "/dev", "/dev", "--bind", tmpdir(), tmpdir()];
  for (const directory of ["/usr/share", "/usr/lib", "/etc"]) {
    args.push("--overlay-src", directory, "--tmp-overlay", directory);
  }
  for (const directory of ["usr/share/openvpn-proxy", "usr/share/chromium", "usr/share/google-chrome", "usr/lib/openvpn-proxy", "etc/chromium", "etc/opt"]) {
    args.push("--ro-bind", join(packageRoot, directory), `/${directory}`);
  }
  args.push("--setenv", "PACKAGE_NAMESPACE", "1", "--", process.execPath, fileURLToPath(import.meta.url));
  const result = spawnSync("bwrap", args, { stdio: "inherit" });
  process.exit(result.status ?? 1);
}
const temp = mkdtempSync(join(tmpdir(), "openvpn-extension-test-"));
let browser;
try {
  const extension = join(temp, "data/extension");
  const packaged = process.env.PACKAGE_ROOT;
  let id;
  if (packaged) {
    id = readdirSync(join(packaged, "usr/share/chromium/extensions"))[0].replace(/\.json$/, "");
  } else {
    execFileSync("python3", [join(root, "install-extension.py"), "--prefix", join(temp, "data"), "--config-home", join(temp, "config"), "--no-open"]);
    const manifest = JSON.parse(readFileSync(join(extension, "manifest.json")));
    const digest = createHash("sha256").update(Buffer.from(manifest.key, "base64")).digest("hex").slice(0, 32);
    id = [...digest].map(c => String.fromCharCode(97 + parseInt(c, 16))).join("");
  }
  const browserArgs = [
    "--headless", "--disable-gpu", "--no-first-run", "--disable-background-networking", "--remote-debugging-pipe",
    `--user-data-dir=${join(temp, "config/chromium")}`
  ];
  const executable = process.env.CHROMIUM_PATH || "chromium";
  if (packaged) {
    // Bubblewrap remaps ownership, so Chromium's setuid helper cannot work.
    // This disposable browser opens only our local extension, inside bwrap.
    browserArgs.push("--no-sandbox");
  } else {
    browserArgs.push(`--load-extension=${extension}`, `--disable-extensions-except=${extension}`);
  }
  browser = spawn(executable, browserArgs, { env: { ...process.env, XDG_CONFIG_HOME: join(temp, "config") }, stdio: ["ignore", "ignore", "pipe", "pipe", "pipe"] });
  let sequence = 0;
  let buffer = "";
  const pending = new Map();
  browser.stderr.on("data", chunk => { if (process.env.BROWSER_DEBUG) process.stderr.write(chunk); });
  browser.stdio[3].on("error", error => {
    for (const respond of pending.values()) respond({ error: error.message });
    pending.clear();
  });
  browser.stdio[4].on("data", chunk => {
    buffer += chunk.toString();
    let end;
    while ((end = buffer.indexOf("\0")) >= 0) {
      const message = JSON.parse(buffer.slice(0, end));
      buffer = buffer.slice(end + 1);
      if (pending.has(message.id)) {
        pending.get(message.id)(message);
        pending.delete(message.id);
      }
    }
  });
  function call(method, params = {}, sessionId) {
    return new Promise((resolve, reject) => {
      const requestId = ++sequence;
      const timeout = setTimeout(() => { pending.delete(requestId); reject(new Error(`Timed out: ${method}`)); }, 10000);
      pending.set(requestId, message => {
        clearTimeout(timeout);
        if (message.error) reject(new Error(JSON.stringify(message.error)));
        else resolve(message.result);
      });
      browser.stdio[3].write(JSON.stringify({ id: requestId, method, params, sessionId }) + "\0");
    });
  }
  if (packaged) {
    let installed = false;
    for (let attempt = 0; attempt < 80; attempt++) {
      const targets = await call("Target.getTargets");
      installed = targets.targetInfos.some(target => target.url.startsWith(`chrome-extension://${id}/`));
      if (installed) break;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
    assert.ok(installed, "Packaged extension must install automatically without --load-extension");
  }
  const { targetId } = await call("Target.createTarget", { url: `chrome-extension://${id}/popup.html` });
  const { sessionId } = await call("Target.attachToTarget", { targetId, flatten: true });
  async function evaluate(expression) {
    const result = await call("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true }, sessionId);
    if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  }
  let status;
  for (let attempt = 0; attempt < 80; attempt++) {
    status = await evaluate('document.getElementById("status")?.textContent');
    if (status && status !== "Checking proxy…") break;
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert.match(status, /SOCKS5 ready|Proxy unavailable on 127\.0\.0\.1:1080|Port 1080 is open/);
  const added = await evaluate('chrome.runtime.sendMessage({action: "add", host: "example.com"})');
  assert.deepEqual(added.sites, ["example.com"]);
  const settings = await evaluate('chrome.proxy.settings.get({incognito: false})');
  assert.equal(settings.levelOfControl, "controlled_by_this_extension");
  assert.equal(settings.value.mode, "pac_script");
  assert.equal(settings.value.pacScript.mandatory, true);
  const removed = await evaluate('chrome.runtime.sendMessage({action: "remove", host: "example.com"})');
  assert.deepEqual(removed.sites, []);
  console.log("Chromium smoke test passed: popup, native checker, whitelist, and proxy settings.");
} finally {
  if (browser && browser.exitCode === null) {
    browser.kill("SIGTERM");
    await new Promise(resolve => browser.once("exit", resolve));
  }
  rmSync(temp, { recursive: true, force: true });
}
