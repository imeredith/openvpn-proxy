import { makePac, normalizeHost } from "./rules.mjs";

const HOST = "org.openvpn_socks.check";
let queue = Promise.resolve();
const serial = task => {
  const result = queue.then(task);
  queue = result.catch(() => {});
  return result;
};
const getSites = async () => (await chrome.storage.local.get({ sites: [] })).sites;

async function apply(sites) {
  const current = await chrome.proxy.settings.get({ incognito: false });
  if (!["controllable_by_this_extension", "controlled_by_this_extension"].includes(current.levelOfControl)) {
    throw new Error("Another extension or browser policy controls the proxy. Disable it before using this extension.");
  }
  if (sites.length) {
    await chrome.proxy.settings.set({ scope: "regular", value: {
      mode: "pac_script", pacScript: { data: makePac(sites), mandatory: true }
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
  let status;
  try {
    status = await chrome.runtime.sendNativeMessage(HOST, { command: "check" });
  } catch {
    status = { ok: false, message: "Proxy checker unavailable. Run the installer, then reload the extension." };
  }
  const sites = await getSites();
  const control = await chrome.proxy.settings.get({ incognito: false });
  if (sites.length && control.levelOfControl !== "controlled_by_this_extension") {
    status = { ok: false, message: "Proxy rules are not active. Another extension or browser policy may control the proxy." };
  }
  await chrome.action.setBadgeText({ text: status.ok ? (sites.length ? "ON" : "") : "!" });
  await chrome.action.setBadgeBackgroundColor({ color: status.ok ? "#147d55" : "#b83932" });
  return { sites, status };
}

async function initialize() {
  await chrome.alarms.create("proxy-check", { periodInMinutes: 1 });
  await apply(await getSites());
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
    if (message.action === "add" || message.action === "remove") {
      const host = normalizeHost(message.host);
      const oldSites = await getSites();
      const sites = message.action === "add" ? [...new Set([...oldSites, host])].sort() : oldSites.filter(site => site !== host);
      try {
        await apply(sites);
        await chrome.storage.local.set({ sites });
      } catch (error) {
        await apply(oldSites).catch(report);
        throw error;
      }
    } else if (message.action !== "status") {
      throw new Error("Unknown action.");
    }
    return check();
  }).then(respond, error => respond({ error: error.message }));
  return true;
});
