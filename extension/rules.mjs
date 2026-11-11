export function normalizeHost(value) {
  const input = value.trim();
  if (!input || /[\s/@:#?\\]/.test(input)) throw new Error("Enter a hostname, such as example.com (no URL or port).");
  const host = new URL(`https://${input}`).hostname.toLowerCase().replace(/\.$/, "");
  if (host.length > 253 || !host.split(".").every(label => /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(label))) {
    throw new Error("Enter a valid hostname.");
  }
  return host;
}

export const DEFAULT_PROXY = "127.0.0.1:1080";

// Returns "host:port" for a SOCKS5 proxy given as a hostname or IPv4 address.
export function normalizeProxy(value) {
  const match = String(value).trim().match(/^([^:]+)(?::(\d{1,5}))?$/);
  const port = Number(match?.[2] ?? 1080);
  if (!match || port < 1 || port > 65535) throw new Error("Enter the proxy as host:port, such as 192.168.1.5:1080.");
  return `${normalizeHost(match[1])}:${port}`;
}

export function matchingRule(host, sites) {
  host = host.toLowerCase().replace(/\.$/, "");
  return sites.find(site => host === site || host.endsWith(`.${site}`));
}

export function makePac(sites, proxy = DEFAULT_PROXY) {
  const safeSites = [...new Set(sites.map(normalizeHost))];
  const route = JSON.stringify(`SOCKS5 ${normalizeProxy(proxy)}`);
  return `function FindProxyForURL(url, host) {
    host = host.toLowerCase().replace(/\\.$/, "");
    var sites = ${JSON.stringify(safeSites)};
    for (var i = 0; i < sites.length; i++) {
      if (host === sites[i] || host.slice(-(sites[i].length + 1)) === "." + sites[i]) {
        return ${route};
      }
    }
    return "DIRECT";
  }`;
}
