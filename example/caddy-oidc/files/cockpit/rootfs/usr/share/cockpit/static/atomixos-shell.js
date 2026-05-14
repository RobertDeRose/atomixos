(function () {
  "use strict";

  const icons = {
    overview: '<svg viewBox="0 0 16 16"><path fill-rule="evenodd" d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1ZM2.9 6.4a5.6 5.6 0 0 1 10.2 0h-2.2c-.2-1.2-.6-2.3-1.1-3A5.6 5.6 0 0 1 8 3.1c-.6 0-1.2.1-1.8.3-.5.7-.9 1.8-1.1 3H2.9Zm-.4 1.2a5.5 5.5 0 0 0 0 .8h2.4V8c0-.1 0-.3.1-.4H2.5Zm3.7 0V8c0 .1 0 .3.1.4h3.4V8c0-.1 0-.3-.1-.4H6.2Zm4.8 0V8c0 .1 0 .3-.1.4h2.6a5.5 5.5 0 0 0 0-.8H11Zm2.1 2H11c-.2 1.2-.6 2.3-1.1 3a5.6 5.6 0 0 0 3.2-3Zm-3.4 0H6.3c.3 1.7 1 2.8 1.7 2.8s1.4-1.1 1.7-2.8Zm-4.6 0H2.9a5.6 5.6 0 0 0 3.2 3c-.4-.7-.8-1.8-1-3Zm1.2-3.2h3.4c-.3-1.7-1-2.8-1.7-2.8S6.6 4.7 6.3 6.4Z"/></svg>',
    logs: '<svg viewBox="0 0 16 16"><path d="M3 1.5h7.5L13 4v10.5H3v-13Zm2 4h6v-1H5v1Zm0 3h6v-1H5v1Zm0 3h4v-1H5v1Z"/></svg>',
    podman: '<svg viewBox="0 0 16 16"><path d="M2 4.5 8 1l6 3.5v7L8 15l-6-3.5v-7Zm2 1.1v4.8l4 2.3 4-2.3V5.6L8 3.3 4 5.6Zm2 1.1 2-1.1 2 1.1v2.6l-2 1.1-2-1.1V6.7Z"/></svg>',
    accounts: '<svg viewBox="0 0 24 24"><path fill-rule="evenodd" clip-rule="evenodd" d="M5 9.5C5 7.01472 7.01472 5 9.5 5C11.9853 5 14 7.01472 14 9.5C14 11.9853 11.9853 14 9.5 14C7.01472 14 5 11.9853 5 9.5Z"/><path d="M14.3675 12.0632C14.322 12.1494 14.3413 12.2569 14.4196 12.3149C15.0012 12.7454 15.7209 13 16.5 13C18.433 13 20 11.433 20 9.5C20 7.567 18.433 6 16.5 6C15.7209 6 15.0012 6.2546 14.4196 6.68513C14.3413 6.74313 14.322 6.85058 14.3675 6.93679C14.7714 7.70219 15 8.5744 15 9.5C15 10.4256 14.7714 11.2978 14.3675 12.0632Z"/><path fill-rule="evenodd" clip-rule="evenodd" d="M4.64115 15.6993C5.87351 15.1644 7.49045 15 9.49995 15C11.5112 15 13.1293 15.1647 14.3621 15.7008C15.705 16.2847 16.5212 17.2793 16.949 18.6836C17.1495 19.3418 16.6551 20 15.9738 20H3.02801C2.34589 20 1.85045 19.3408 2.05157 18.6814C2.47994 17.2769 3.29738 16.2826 4.64115 15.6993Z"/><path d="M14.8185 14.0364C14.4045 14.0621 14.3802 14.6183 14.7606 14.7837C15.803 15.237 16.5879 15.9043 17.1508 16.756C17.6127 17.4549 18.33 18 19.1677 18H20.9483C21.6555 18 22.1715 17.2973 21.9227 16.6108C21.9084 16.5713 21.8935 16.5321 21.8781 16.4932C21.5357 15.6286 20.9488 14.9921 20.0798 14.5864C19.2639 14.2055 18.2425 14.0483 17.0392 14.0008L17.0194 14H16.9997C16.2909 14 15.5506 13.9909 14.8185 14.0364Z"/></svg>',
    services: '<svg viewBox="0 0 24 24"><path fill="none" stroke="currentColor" stroke-width="2" d="M6,9 C7.65685425,9 9,7.65685425 9,6 C9,4.34314575 7.65685425,3 6,3 C4.34314575,3 3,4.34314575 3,6 C3,7.65685425 4.34314575,9 6,9 Z M6,3 L6,0 M6,12 L6,9 M0,6 L3,6 M9,6 L12,6 M2,2 L4,4 M8,8 L10,10 M10,2 L8,4 M4,8 L2,10 M18,12 C19.6568542,12 21,10.6568542 21,9 C21,7.34314575 19.6568542,6 18,6 C16.3431458,6 15,7.34314575 15,9 C15,10.6568542 16.3431458,12 18,12 Z M18,6 L18,3 M18,15 L18,12 M12,9 L15,9 M21,9 L24,9 M14,5 L16,7 M20,11 L22,13 M22,5 L20,7 M16,11 L14,13 M9,21 C10.6568542,21 12,19.6568542 12,18 C12,16.3431458 10.6568542,15 9,15 C7.34314575,15 6,16.3431458 6,18 C6,19.6568542 7.34314575,21 9,21 Z M9,15 L9,12 M9,24 L9,21 M3,18 L6,18 M12,18 L15,18 M5,14 L7,16 M11,20 L13,22 M13,14 L11,16 M7,20 L5,22"/></svg>',
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

    const theme = window.localStorage && window.localStorage.getItem("shell:style");
    if (theme === "dark" || theme === "light") return theme;

    return window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function bridgeThemeForAuthPortal() {
    window.localStorage && window.localStorage.setItem("shell:style", activeTheme());
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
    return Array.from(document.querySelectorAll("#nav-system, .pf-v6-c-page__sidebar"));
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
    new MutationObserver(onMutation).observe(document.documentElement, {
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
