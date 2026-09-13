export function normalizeHost(value) {
  const input = value.trim();
  if (!input || /[\s/@:#?\\]/.test(input)) throw new Error("Enter a hostname, such as example.com (no URL or port).");
  const host = new URL(`https://${input}`).hostname.toLowerCase().replace(/\.$/, "");
  if (host.length > 253 || !host.split(".").every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) {
    throw new Error("Enter a valid hostname.");
  }
  return host;
}

export function matchingRule(host, sites) {
  host = host.toLowerCase().replace(/\.$/, "");
  return sites.find(site => host === site || host.endsWith(`.${site}`));
}

export function makePac(sites) {
  const safeSites = [...new Set(sites.map(normalizeHost))];
  return `function FindProxyForURL(url, host) {
    host = host.toLowerCase().replace(/\\.$/, "");
    var sites = ${JSON.stringify(safeSites)};
    for (var i = 0; i < sites.length; i++) {
      if (host === sites[i] || host.slice(-(sites[i].length + 1)) === "." + sites[i]) {
        return "SOCKS5 127.0.0.1:1080";
      }
    }
    return "DIRECT";
  }`;
}
