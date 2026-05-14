(function () {
  "use strict";

  const icons = {
    overview: '<svg viewBox="0 0 16 16"><path fill-rule="evenodd" d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1ZM2.9 6.4a5.6 5.6 0 0 1 10.2 0h-2.2c-.2-1.2-.6-2.3-1.1-3A5.6 5.6 0 0 1 8 3.1c-.6 0-1.2.1-1.8.3-.5.7-.9 1.8-1.1 3H2.9Zm-.4 1.2a5.5 5.5 0 0 0 0 .8h2.4V8c0-.1 0-.3.1-.4H2.5Zm3.7 0V8c0 .1 0 .3.1.4h3.4V8c0-.1 0-.3-.1-.4H6.2Zm4.8 0V8c0 .1 0 .3-.1.4h2.6a5.5 5.5 0 0 0 0-.8H11Zm2.1 2H11c-.2 1.2-.6 2.3-1.1 3a5.6 5.6 0 0 0 3.2-3Zm-3.4 0H6.3c.3 1.7 1 2.8 1.7 2.8s1.4-1.1 1.7-2.8Zm-4.6 0H2.9a5.6 5.6 0 0 0 3.2 3c-.4-.7-.8-1.8-1-3Zm1.2-3.2h3.4c-.3-1.7-1-2.8-1.7-2.8S6.6 4.7 6.3 6.4Z"/></svg>',
    logs: '<svg viewBox="0 0 16 16"><path d="M3 1.5h7.5L13 4v10.5H3v-13Zm2 4h6v-1H5v1Zm0 3h6v-1H5v1Zm0 3h4v-1H5v1Z"/></svg>',
    podman: '<svg viewBox="0 0 16 16"><path d="M2 4.5 8 1l6 3.5v7L8 15l-6-3.5v-7Zm2 1.1v4.8l4 2.3 4-2.3V5.6L8 3.3 4 5.6Zm2 1.1 2-1.1 2 1.1v2.6l-2 1.1-2-1.1V6.7Z"/></svg>',
    accounts: '<svg viewBox="0 0 16 16"><path d="M8 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm-5 6c.4-2.6 2.5-4.5 5-4.5s4.6 1.9 5 4.5H3Z"/></svg>',
    services: '<svg viewBox="0 0 16 16"><path fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" d="M4 6a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm0-4V1m0 6.5V6M1 4h1.5m3 0H7M1.9 1.9l1 1m2.2 2.2 1 1m0-5.2-1 1M5.1 5.1l-1 1M12 8a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm0-4V3m0 6.5V8M9 6h1.5m3 0H15M9.9 3.9l1 1m2.2 2.2 1 1m0-5.2-1 1m-2.2 2.2-1 1M6 14a2 2 0 1 0 0-4 2 2 0 0 0 0 4Zm0-4v-1m0 6.5V14M3 12h1.5m3 0H9M3.9 9.9l1 1m2.2 2.2 1 1m0-5.2-1 1m-2.2 2.2-1 1"/></svg>',
    terminal: '<svg viewBox="0 0 16 16"><path d="M1.5 3h13v10h-13V3Zm2 2.5L5.7 8l-2.2 2.5h1.7L7.4 8 5.2 5.5H3.5Zm4.5 5h4v-1H8v1Z"/></svg>',
    files: '<svg viewBox="0 0 16 16"><path d="M1.5 4.5V13h13V5.5H7.2L5.8 3H1.5v1.5Zm1 1h3.9l1.4 2.5h5.7v4h-11V5.5Z"/></svg>',
  };

  function cookieValue(name) {
    const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const match = document.cookie.match(new RegExp("(?:^|;\\s*)" + escaped + "=([^;]+)"));
    return match && decodeURIComponent(match[1]);
  }

  function activeTheme() {
    if (document.documentElement.classList.contains("pf-v6-theme-dark")) return "dark";
    if (document.documentElement.classList.contains("pf-v6-theme-light")) return "light";

    const theme = cookieValue("cockpit:theme");
    if (theme === "dark" || theme === "light") return theme;

    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function bridgeThemeForAuthPortal() {
    document.cookie = "cockpit:theme=" + encodeURIComponent(activeTheme()) + "; path=/; SameSite=Lax";
  }

  function routeLogout(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    bridgeThemeForAuthPortal();
    window.location.assign("/auth/logout?redirect_url=/auth/portal");
  }

  function hookLogout() {
    const button = document.getElementById("logout");
    if (!button || button.dataset.atomixosLogoutHook === "1") {
      return;
    }
    button.dataset.atomixosLogoutHook = "1";
    button.addEventListener("click", routeLogout, true);
  }

  function removeInjectedBrand() {
    document.querySelectorAll(".atomixos-host-brand").forEach((brand) => {
      const switcher = brand.querySelector(".ct-switcher");
      if (switcher) {
        brand.replaceWith(switcher);
      } else {
        brand.remove();
      }
    });
  }

  function sidebarElements() {
    return Array.from(document.querySelectorAll("#nav-system, #host-apps, .pf-v6-c-page__sidebar, nav[aria-label='Global'], nav[aria-label='Main']"));
  }

  let sidebarTimer = 0;

  function scheduleSidebarExpanded(expanded) {
    window.clearTimeout(sidebarTimer);
    sidebarTimer = window.setTimeout(() => setSidebarExpanded(expanded), expanded ? 120 : 220);
  }

  function setSidebarExpanded(expanded) {
    document.body.classList.toggle("atomixos-sidebar-expanded", expanded);
  }

  function hookSidebarExpansion() {
    sidebarElements().forEach((element) => {
      if (element.dataset.atomixosSidebarHook === "1") {
        return;
      }
      element.dataset.atomixosSidebarHook = "1";
      element.addEventListener("pointerenter", () => scheduleSidebarExpanded(true));
      element.addEventListener("pointerleave", () => scheduleSidebarExpanded(false));
      element.addEventListener("focusin", () => scheduleSidebarExpanded(true));
      element.addEventListener("focusout", (event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) {
          scheduleSidebarExpanded(false);
        }
      });
    });
  }

  function placeSidebarSearch() {
    const hostApps = document.getElementById("host-apps");
    const search = hostApps && hostApps.querySelector(":scope > .search, :scope > .pf-v6-c-text-input-group.search");
    const firstSection = hostApps && hostApps.querySelector("nav, .pf-v6-c-nav, .pf-v6-c-nav__section, h2");
    if (!hostApps || !search || search.dataset.atomixosPlaced === "1") {
      return;
    }
    search.dataset.atomixosPlaced = "1";
    if (firstSection && firstSection.previousElementSibling !== search) {
      hostApps.insertBefore(search, firstSection);
    }
  }

  function normalizeText(text) {
    return text.trim().toLowerCase().replace(/\s+/g, " ");
  }

  function iconFor(text) {
    const key = normalizeText(text);
    if (key.includes("podman")) return icons.podman;
    if (key.includes("file")) return icons.files;
    if (key.includes("overview")) return icons.overview;
    if (key.includes("log")) return icons.logs;
    if (key.includes("account")) return icons.accounts;
    if (key.includes("service")) return icons.services;
    if (key.includes("terminal")) return icons.terminal;
    return key.slice(0, 1).toUpperCase();
  }

  function decorateNav() {
    document.querySelectorAll('nav[aria-label="Global"] a, nav[aria-label="Main"] a, .pf-v6-c-nav__link').forEach((link) => {
      if (link.dataset.atomixosNavDecorated === "1") {
        return;
      }
      const labelText = link.textContent.trim();
      if (!labelText) {
        return;
      }
      link.dataset.atomixosNavDecorated = "1";
      const existing = Array.from(link.childNodes);
      const icon = document.createElement("span");
      icon.className = "atomixos-nav-icon";
      icon.innerHTML = iconFor(labelText);
      const label = document.createElement("span");
      label.className = "atomixos-nav-label";
      existing.forEach((node) => label.appendChild(node));
      link.append(icon, label);
    });
  }

  let mutationTimer = 0;

  function onMutation() {
    window.clearTimeout(mutationTimer);
    mutationTimer = window.setTimeout(() => {
      hookLogout();
      removeInjectedBrand();
      placeSidebarSearch();
      hookSidebarExpansion();
      decorateNav();
    }, 80);
  }

  function init() {
    document.body.classList.add("atomixos-sidebar-collapsed");
    hookLogout();
    removeInjectedBrand();
    placeSidebarSearch();
    hookSidebarExpansion();
    decorateNav();
    // Observe the shell container rather than the entire document to avoid
    // firing on terminal output and other high-frequency DOM changes.
    const target = document.getElementById("shell") || document.body;
    new MutationObserver(onMutation).observe(target, {
      childList: true,
      subtree: true,
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
