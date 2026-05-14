(function () {
  function applyTheme() {
    const cookie = document.cookie.match(/(?:^|;\s*)cockpit:theme=([^;]+)/);
    let theme = cookie && decodeURIComponent(cookie[1]);
    if (theme !== "light" && theme !== "dark") {
      theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    document.documentElement.classList.remove("pf-v6-theme-light", "pf-v6-theme-dark");
    document.documentElement.classList.add("pf-v6-theme-" + theme);
    // CSS custom properties are defined in atomixos-auth.css on :root and
    // :root.pf-v6-theme-dark — toggling the class is sufficient.
  }

  function nextTheme() {
    return document.documentElement.classList.contains("pf-v6-theme-dark") ? "light" : "dark";
  }

  function setTheme(theme) {
    document.cookie = "cockpit:theme=" + encodeURIComponent(theme) + "; path=/; SameSite=Lax";
    document.cookie = "cockpit:theme=" + encodeURIComponent(theme) + "; path=/cockpit/; SameSite=Lax";
    applyTheme();
    updateThemeToggle();
  }

  function themeIcon() {
    if (document.documentElement.classList.contains("pf-v6-theme-dark")) {
      return '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 1.2a.8.8 0 0 1 .8.8v1a.8.8 0 0 1-1.6 0V2a.8.8 0 0 1 .8-.8Zm0 10.6A3.8 3.8 0 1 0 8 4.2a3.8 3.8 0 0 0 0 7.6Zm0 1.2a.8.8 0 0 1 .8.8v.2a.8.8 0 0 1-1.6 0v-.2A.8.8 0 0 1 8 13Zm6-5.8a.8.8 0 0 1 0 1.6h-1a.8.8 0 0 1 0-1.6h1ZM3 8a.8.8 0 0 1-.8.8H2a.8.8 0 1 1 0-1.6h.2A.8.8 0 0 1 3 8Zm9.9-4.9a.8.8 0 0 1 0 1.1l-.7.7a.8.8 0 1 1-1.1-1.1l.7-.7a.8.8 0 0 1 1.1 0ZM4.9 11.1a.8.8 0 0 1 0 1.1l-.7.7a.8.8 0 0 1-1.1-1.1l.7-.7a.8.8 0 0 1 1.1 0Zm7.3 0 .7.7a.8.8 0 0 1-1.1 1.1l-.7-.7a.8.8 0 0 1 1.1-1.1ZM4.2 3.1l.7.7a.8.8 0 1 1-1.1 1.1l-.7-.7a.8.8 0 0 1 1.1-1.1Z"/></svg>';
    }
    return '<svg viewBox="0 0 16 16" aria-hidden="true"><path d="M10.8 13.7A6.3 6.3 0 0 1 7.6 1.4a5.1 5.1 0 1 0 6.9 6.9 6.3 6.3 0 0 1-3.7 5.4Z"/></svg>';
  }

  function updateThemeToggle() {
    const button = document.querySelector(".atomixos-theme-toggle");
    if (!button) return;

    const theme = document.documentElement.classList.contains("pf-v6-theme-dark") ? "dark" : "light";
    button.innerHTML = themeIcon();
    button.setAttribute("aria-label", theme === "dark" ? "Switch to light theme" : "Switch to dark theme");
    button.title = button.getAttribute("aria-label");
  }

  function textOf(node) {
    return (node.textContent || "").replace(/\s+/g, " ").trim();
  }

  function prependBrand() {
    const logo = document.querySelector(".logo-img");
    if (logo) {
      logo.src = "/auth/assets/images/atomixos-logo.png";
      logo.alt = "AtomixOS";
      return;
    }

    if (!document.querySelector(".atomixos-auth-brand")) {
      const target = document.querySelector(".app-container") || document.body.firstElementChild;
      if (!target || !target.parentNode) return;

      const brand = document.createElement("div");
      brand.className = "atomixos-auth-brand";
      brand.innerHTML = '<img src="/auth/assets/images/atomixos-logo.png" alt="AtomixOS">';
      target.parentNode.insertBefore(brand, target);
    }

    const container = document.querySelector(".app-container");
    if (container) {
      container.style.position = "relative";
      container.style.background = "color-mix(in srgb, var(--anx-surface) 96%, transparent)";
      container.style.borderColor = "color-mix(in srgb, var(--anx-border) 70%, transparent)";
      container.style.borderRadius = "0";
      container.style.color = "var(--anx-text)";
    }
  }

  function decorateThemeToggle() {
    const existing = document.querySelector(".atomixos-theme-toggle");
    if (existing) {
      if (existing.dataset.atomixosThemeHook !== "1") {
        existing.dataset.atomixosThemeHook = "1";
        existing.addEventListener("click", () => setTheme(nextTheme()));
      }
      updateThemeToggle();
      return;
    }

    const button = document.createElement("button");
    button.type = "button";
    button.className = "atomixos-theme-toggle";
    button.dataset.atomixosThemeHook = "1";
    button.addEventListener("click", () => setTheme(nextTheme()));
    document.body.appendChild(button);
    updateThemeToggle();
  }

  function decorateCards() {
    const headings = Array.from(document.querySelectorAll("h1,h2,h3"));
    for (const heading of headings) {
      const card = heading.closest("main,section,article,form,div");
      if (card && !card.classList.contains("logo-box") && !card.classList.contains("logo-col-box")) {
        card.classList.add("atomixos-auth-card");
      }
    }

    for (const card of document.querySelectorAll(".logo-col-box .atomixos-auth-card")) {
      Object.assign(card.style, {
        border: "0",
        borderRadius: "0",
        background: "transparent",
        boxShadow: "none",
      });
    }

    const logoBox = document.querySelector(".logo-box");
    if (logoBox) {
      Object.assign(logoBox.style, {
        border: "0",
        borderRadius: "0",
        background: "transparent",
        boxShadow: "none",
        outline: "0",
      });
    }

    for (const heading of document.querySelectorAll(".logo-txt,.logo-col-txt")) {
      Object.assign(heading.style, {
        display: "block",
        margin: "0",
        border: "0",
        borderRadius: "0",
        background: "transparent",
        boxShadow: "none",
        outline: "0",
      });
    }
  }

  function decorateProviderLinks() {
    const candidates = Array.from(document.querySelectorAll("a,button"));
    for (const node of candidates) {
      const label = textOf(node);
      const href = node.getAttribute("href") || "";
      if (/azure|microsoft|entra/i.test(label + " " + href)) {
        node.classList.add("atomixos-provider-entra");
        const text = node.querySelector(".app-login-btn-txt span") || node;
        text.textContent = "Microsoft Entra";
        text.style.color = "var(--anx-text)";
        text.style.textTransform = "none";
      }
    }
  }

  function decoratePortalLinks() {
    for (const label of document.querySelectorAll(".app-inp-lbl")) {
      if (/access the following services/i.test(textOf(label))) {
        label.style.display = "none";
      }
    }

    for (const box of document.querySelectorAll(".app-portal-btn-img")) {
      box.style.width = "3.75rem";
      box.style.minWidth = "3.75rem";
      box.style.background = "linear-gradient(135deg, #0078d4, #50e6ff)";
      box.style.color = "#ffffff";
    }

    for (const icon of document.querySelectorAll(".app-portal-btn-img i")) {
      icon.style.color = "#ffffff";
    }

    for (const node of document.querySelectorAll(".app-portal-btn-box,.app-portal-btn-txt,.app-login-btn-box")) {
      node.style.setProperty("background", "var(--anx-button)", "important");
      node.style.color = "var(--anx-text)";
    }

    for (const node of document.querySelectorAll('a[href*="/cockpit/"]')) {
      node.childNodes.forEach((child) => {
        if (child.nodeType === Node.TEXT_NODE && /cockpit/i.test(child.textContent || "")) {
          child.textContent = child.textContent.replace(/Cockpit/gi, "Admin Console");
        }
      });

      const iconBox = node.querySelector(".app-portal-btn-img");
      if (iconBox) {
        Object.assign(iconBox.style, {
          display: "grid",
          placeItems: "center",
          width: "3.75rem",
          minWidth: "3.75rem",
          height: "4rem",
          background: "linear-gradient(135deg, #0078d4, #50e6ff)",
          borderRadius: "0.375rem 0 0 0.375rem",
          color: "var(--anx-accent)",
        });
      }
    }
  }

  function injectPortalIconStyle() {
    if (document.getElementById("atomixos-auth-runtime-style")) return;

    const style = document.createElement("style");
    style.id = "atomixos-auth-runtime-style";
    style.textContent = `
      .atomixos-theme-toggle {
        background: transparent !important;
      }
      a[href*="/cockpit/"] .app-portal-btn-img {
        display: grid !important;
        place-items: center !important;
        width: 3.75rem !important;
        min-width: 3.75rem !important;
        height: 4rem !important;
        background: linear-gradient(135deg, #0078d4, #50e6ff) !important;
        border-radius: 0.375rem 0 0 0.375rem !important;
        color: var(--anx-accent) !important;
      }
      .app-portal-btn-img {
        width: 3.75rem !important;
        min-width: 3.75rem !important;
        background: linear-gradient(135deg, #0078d4, #50e6ff) !important;
        color: #ffffff !important;
      }
      .app-portal-btn-img i {
        color: #ffffff !important;
      }
      .app-portal-btn-box,
      .app-portal-btn-txt,
      .app-login-btn-txt,
      .app-login-btn-box {
        background: var(--anx-button) !important;
        color: var(--anx-text) !important;
      }
      .app-portal-btn-box {
        border: 1px solid color-mix(in srgb, var(--anx-border) 65%, transparent) !important;
        box-shadow: none !important;
        overflow: hidden !important;
      }
      .app-login-btn-txt span {
        color: var(--anx-text) !important;
        text-transform: none !important;
      }
      a[href*="/cockpit/"] .app-portal-btn-img i {
        display: none !important;
      }
      a[href*="/cockpit/"] .app-portal-btn-img::before {
        content: "";
        display: inline-block;
        width: 1.65rem;
        height: 1.65rem;
        background: #ffffff;
        mask: url("/auth/assets/images/cockpit.svg") center / contain no-repeat;
        -webkit-mask: url("/auth/assets/images/cockpit.svg") center / contain no-repeat;
      }
    `;
    document.head.appendChild(style);
  }

  function apply() {
    applyTheme();
    prependBrand();
    decorateThemeToggle();
    decorateCards();
    decorateProviderLinks();
    decoratePortalLinks();
    injectPortalIconStyle();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", apply, { once: true });
  } else {
    apply();
  }
})();
