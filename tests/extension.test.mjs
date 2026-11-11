import test from "node:test";
import assert from "node:assert/strict";
import vm from "node:vm";
import { makePac, matchingRule, normalizeHost, normalizeProxy } from "../extension/rules.mjs";

test("PAC proxies exact hosts and subdomains without DNS lookups or direct fallback", () => {
  const context = vm.createContext({});
  vm.runInContext(makePac(["example.com", "other.test"]), context);
  for (const host of ["example.com", "img.example.com", "EXAMPLE.COM.", "other.test"]) {
    assert.equal(context.FindProxyForURL(`https://${host}/`, host), "SOCKS5 127.0.0.1:1080");
  }
  for (const host of ["example.com.evil.test", "notexample.com", "unlisted.test"]) {
    assert.equal(context.FindProxyForURL(`https://${host}/`, host), "DIRECT");
  }
});

test("PAC and proxy setting use a configured LAN proxy without injection", () => {
  const context = vm.createContext({});
  vm.runInContext(makePac(["example.com"], "192.168.1.5:1081"), context);
  assert.equal(context.FindProxyForURL("https://example.com/", "example.com"), "SOCKS5 192.168.1.5:1081");
  assert.equal(normalizeProxy(" Proxy.LAN "), "proxy.lan:1080");
  for (const value of ["", "host:0", "host:65536", "host:", "http://host:1080", "[::1]:1080", 'a";return "DIRECT";:1080']) {
    assert.throws(() => normalizeProxy(value), undefined, value);
  }
});

test("hostname validation rejects URLs and PAC injection and supports IDNs", () => {
  assert.equal(normalizeHost(" EXAMPLE.com. "), "example.com");
  assert.equal(normalizeHost("bücher.de"), "xn--bcher-kva.de");
  for (const value of ["", "https://example.com", "example.com:1080", "a/b", "*.example.com", 'a\");return "DIRECT";', "-bad.com"]) {
    assert.throws(() => normalizeHost(value));
  }
  assert.equal(matchingRule("www.example.com", ["example.com"]), "example.com");
  assert.equal(matchingRule("notexample.com", ["example.com"]), undefined);
});

test("service worker persists rules and keeps them active when the proxy is unavailable", async () => {
  let listener;
  let stored = { sites: [] };
  let config;
  let control = "controllable_by_this_extension";
  let available = true;
  let checked;
  const setting = { set: async () => {}, clear: async () => {} };
  globalThis.chrome = {
    storage: { local: { get: async defaults => ({ ...defaults, ...stored }), set: async value => { stored = value; } } },
    proxy: { settings: {
      get: async () => ({ levelOfControl: control }),
      set: async value => { config = value; control = "controlled_by_this_extension"; },
      clear: async () => { config = undefined; control = "controllable_by_this_extension"; }
    } },
    privacy: { network: { networkPredictionEnabled: setting, webRTCIPHandlingPolicy: setting } },
    action: { setBadgeText: async () => {}, setBadgeBackgroundColor: async () => {} },
    alarms: { onAlarm: { addListener: () => {} }, create: async () => {} },
    runtime: {
      id: "test",
      sendNativeMessage: async (host, message) => (checked = message, { ok: available, message: available ? "ready" : "unavailable" }),
      onInstalled: { addListener: () => {} }, onStartup: { addListener: () => {} },
      onMessage: { addListener: handler => { listener = handler; } }
    }
  };
  await import("../extension/background.js");
  const send = message => new Promise(resolve => listener(message, { id: "test" }, resolve));
  assert.equal((await send({ action: "add", host: "example.com" })).status.ok, true);
  assert.deepEqual(stored.sites, ["example.com"]);
  assert.equal(config.value.pacScript.mandatory, true);
  assert.match(config.value.pacScript.data, /SOCKS5 127\.0\.0\.1:1080/);
  assert.deepEqual(checked, { command: "check", host: "127.0.0.1", port: 1080 });
  assert.equal((await send({ action: "set-proxy", proxy: "proxy.lan:1081" })).proxy, "proxy.lan:1081");
  assert.equal(stored.proxy, "proxy.lan:1081");
  assert.match(config.value.pacScript.data, /SOCKS5 proxy\.lan:1081/);
  assert.deepEqual(checked, { command: "check", host: "proxy.lan", port: 1081 });
  assert.match((await send({ action: "set-proxy", proxy: "bad:port" })).error, /host:port/);
  assert.equal(stored.proxy, "proxy.lan:1081");
  const activeConfig = config;
  available = false;
  assert.equal((await send({ action: "status" })).status.ok, false);
  assert.equal(config, activeConfig);
  assert.deepEqual((await send({ action: "add", host: "offline.test" })).sites, ["example.com", "offline.test"]);
  await send({ action: "remove", host: "example.com" });
  await send({ action: "remove", host: "offline.test" });
  assert.equal(config, undefined);
  delete globalThis.chrome;
});
