import { matchingRule } from "./rules.mjs";

const $ = id => document.getElementById(id);
let currentHost = "";
let sites = [];

function render(data) {
  sites = data.sites;
  $("status").textContent = data.status.message;
  $("status").className = data.status.ok ? "good" : "bad";
  const matched = matchingRule(currentHost, sites);
  $("current").textContent = currentHost ? `${currentHost} — ${matched ? `proxied by ${matched}` : "direct"}` : "Open an HTTP or HTTPS site to add it.";
  $("toggle").textContent = matched ? `Remove ${matched} from whitelist` : "Add this site to whitelist";
  $("toggle").disabled = !currentHost;
  $("sites").replaceChildren();
  for (const site of sites) {
    const li = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = site;
    const button = document.createElement("button");
    button.textContent = "Remove";
    button.setAttribute("aria-label", `Remove ${site}`);
    button.addEventListener("click", () => request("remove", site));
    li.append(label, button);
    $("sites").append(li);
  }
  if (!sites.length) $("sites").textContent = "No sites added yet.";
}

async function request(action, host) {
  $("error").textContent = "";
  document.querySelectorAll("button").forEach(button => { button.disabled = true; });
  try {
    const data = await chrome.runtime.sendMessage({ action, host });
    if (data.error) throw new Error(data.error);
    render(data);
    return true;
  } catch (error) {
    $("error").textContent = error.message;
    return false;
  } finally {
    document.querySelectorAll("button").forEach(button => { button.disabled = false; });
    $("toggle").disabled = !currentHost;
  }
}

$("check").addEventListener("click", () => request("status"));
$("toggle").addEventListener("click", () => {
  const matched = matchingRule(currentHost, sites);
  request(matched ? "remove" : "add", matched || currentHost);
});
$("add-form").addEventListener("submit", async event => {
  event.preventDefault();
  if (await request("add", $("hostname").value)) $("hostname").value = "";
});
try {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = new URL(tab.url);
  if (["http:", "https:"].includes(url.protocol)) currentHost = url.hostname;
} catch { /* Internal pages do not expose a usable site. */ }
await request("status");
