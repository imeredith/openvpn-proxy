import { DEFAULT_PROXY, makePac, normalizeHost, normalizeProxy } from "./rules.mjs";

const HOST = "org.openvpn_socks.check";
let queue = Promise.resolve();
const serial = task => {
  const result = queue.then(task);
  queue = result.catch(() => {});
  return result;
};
const getState = () => chrome.storage.local.get({ sites: [], proxy: DEFAULT_PROXY });

async function apply({ sites, proxy }) {
  const current = await chrome.proxy.settings.get({ incognito: false });
  if (!["controllable_by_this_extension", "controlled_by_this_extension"].includes(current.levelOfControl)) {
    throw new Error("Another extension or browser policy controls the proxy. Disable it before using this extension.");
  }
  if (sites.length) {
    await chrome.proxy.settings.set({ scope: "regular", value: {
      mode: "pac_script", pacScript: { data: makePac(sites, proxy), mandatory: true }
    } });
    await chrome.privacy.network.networkPredictionEnabled.set({ value: false });
    await chrome.privacy.network.webRTCIPHandlingPolicy.set({ value: "disable_non_proxied_udp" });
  } else {
    await chrome.proxy.settings.clear({ scope: "regular" });
    await chrome.privacy.network.networkPredictionEnabled.clear({});
    await chrome.privacy.network.webRTCIPHandlingPolicy.clear({});
  }
}

async function check() {
  const { sites, proxy } = await getState();
  const [host, port] = proxy.split(":");
  let status;
  try {
    status = await chrome.runtime.sendNativeMessage(HOST, { command: "check", host, port: Number(port) });
  } catch {
    status = { ok: false, message: "Proxy checker unavailable. Run the installer, then reload the extension." };
  }
  const control = await chrome.proxy.settings.get({ incognito: false });
  if (sites.length && control.levelOfControl !== "controlled_by_this_extension") {
    status = { ok: false, message: "Proxy rules are not active. Another extension or browser policy may control the proxy." };
  }
  await chrome.action.setBadgeText({ text: status.ok ? (sites.length ? "ON" : "") : "!" });
  await chrome.action.setBadgeBackgroundColor({ color: status.ok ? "#147d55" : "#b83932" });
  return { sites, proxy, status };
}

async function initialize() {
  await chrome.alarms.create("proxy-check", { periodInMinutes: 1 });
  await apply(await getState());
  return check();
}
function report(error) {
  console.error(error);
  chrome.action.setBadgeText({ text: "!" });
  chrome.action.setBadgeBackgroundColor({ color: "#b83932" });
}
chrome.runtime.onInstalled.addListener(() => serial(initialize).catch(report));
chrome.runtime.onStartup.addListener(() => serial(initialize).catch(report));
chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "proxy-check") serial(check).catch(report);
});
chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (sender.id !== chrome.runtime.id) return false;
  serial(async () => {
    if (["add", "remove", "set-proxy"].includes(message.action)) {
      const old = await getState();
      const state = { ...old };
      if (message.action === "set-proxy") {
        state.proxy = normalizeProxy(message.proxy);
      } else {
        const host = normalizeHost(message.host);
        state.sites = message.action === "add" ? [...new Set([...old.sites, host])].sort() : old.sites.filter(site => site !== host);
      }
      try {
        await apply(state);
        await chrome.storage.local.set(state);
      } catch (error) {
        await apply(old).catch(report);
        throw error;
      }
    } else if (message.action !== "status") {
      throw new Error("Unknown action.");
    }
    return check();
  }).then(respond, error => respond({ error: error.message }));
  return true;
});
