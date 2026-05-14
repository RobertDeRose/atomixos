(function () {
  "use strict";

  const marker = "atomixos-cockpit-autologin-attempted";

  function loginPath() {
    // Cockpit runs behind UrlRoot=/cockpit/, so the internal login endpoint
    // is at /cockpit/cockpit/login — the first segment is the URL root and
    // the second is Cockpit's own /cockpit/login path.
    const path = window.location.pathname;
    const match = path.match(/^(.*\/cockpit)\/?/);
    return (match ? match[1] : "/cockpit") + "/cockpit/login";
  }

  function autologin() {
    if (window.sessionStorage.getItem(marker) === "1") {
      return;
    }
    window.sessionStorage.setItem(marker, "1");

    const request = new XMLHttpRequest();
    request.open("GET", loginPath(), true);
    request.onreadystatechange = function () {
      if (request.readyState !== 4) {
        return;
      }
      if (request.status === 200) {
        window.sessionStorage.removeItem(marker);
        window.setTimeout(function () {
          window.location.assign("/cockpit/system");
        }, 50);
      } else {
        window.sessionStorage.removeItem(marker);
      }
    };
    request.send();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autologin, { once: true });
  } else {
    autologin();
  }
})();
