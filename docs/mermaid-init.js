// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

(() => {
    const darkThemes = ['ayu', 'navy', 'coal'];
    const lightThemes = ['light', 'rust'];
    const mermaidModalId = 'mermaid-diagram-modal';
    const maximizeIcon = `
        <svg viewBox="0 0 448 512" aria-hidden="true" focusable="false">
            <path fill="currentColor" d="M168 32L24 32C10.7 32 0 42.7 0 56L0 200c0 9.7 5.8 18.5 14.8 22.2S34.1 223.8 41 217l40-40 79 79-79 79-40-40c-6.9-6.9-17.2-8.9-26.2-5.2S0 302.3 0 312L0 456c0 13.3 10.7 24 24 24l144 0c9.7 0 18.5-5.8 22.2-14.8s1.7-19.3-5.2-26.2l-40-40 79-79 79 79-40 40c-6.9 6.9-8.9 17.2-5.2 26.2S270.3 480 280 480l144 0c13.3 0 24-10.7 24-24l0-144c0-9.7-5.8-18.5-14.8-22.2s-19.3-1.7-26.2 5.2l-40 40-79-79 79-79 40 40c6.9 6.9 17.2 8.9 26.2 5.2S448 209.7 448 200l0-144c0-13.3-10.7-24-24-24L280 32c-9.7 0-18.5 5.8-22.2 14.8S256.2 66.1 263 73l40 40-79 79-79-79 40-40c6.9-6.9 8.9-17.2 5.2-26.2S177.7 32 168 32z"/>
        </svg>
    `;

    const classList = document.getElementsByTagName('html')[0].classList;

    let lastThemeWasLight = true;
    for (const cssClass of classList) {
        if (darkThemes.includes(cssClass)) {
            lastThemeWasLight = false;
            break;
        }
    }

    const theme = lastThemeWasLight ? 'default' : 'dark';
    mermaid.initialize({ startOnLoad: true, theme });

    const getThemeButton = (themeName) => {
        return document.getElementById(themeName) || document.getElementById(`mdbook-theme-${themeName}`);
    };

    const closeMermaidModal = () => {
        const modal = document.getElementById(mermaidModalId);
        if (!modal) {
            return;
        }

        modal.hidden = true;
        document.body.classList.remove('mermaid-modal-open');
    };

    const openMermaidModal = (sourcePre) => {
        const modal = document.getElementById(mermaidModalId);
        const content = modal?.querySelector('.mermaid-modal__content');
        const title = modal?.querySelector('.mermaid-modal__title');

        if (!modal || !content) {
            return;
        }

        const sourceSvg = sourcePre.querySelector('svg');
        if (!sourceSvg) {
            return;
        }

        content.innerHTML = '';
        const clone = sourceSvg.cloneNode(true);
        clone.style.width = '100%';
        clone.style.height = 'auto';
        clone.style.maxWidth = 'none';
        content.appendChild(clone);

        if (title) {
            const heading = sourcePre.previousElementSibling;
            title.textContent = heading?.textContent?.trim() || 'Diagram';
        }

        modal.hidden = false;
        document.body.classList.add('mermaid-modal-open');
    };

    const ensureMermaidModal = () => {
        let modal = document.getElementById(mermaidModalId);
        if (modal) {
            return modal;
        }

        modal = document.createElement('div');
        modal.id = mermaidModalId;
        modal.className = 'mermaid-modal';
        modal.hidden = true;
        modal.innerHTML = `
            <div class="mermaid-modal__backdrop" data-mermaid-close="true"></div>
            <div class="mermaid-modal__panel" role="dialog" aria-modal="true" aria-labelledby="${mermaidModalId}-title">
                <div class="mermaid-modal__header">
                    <strong id="${mermaidModalId}-title" class="mermaid-modal__title">Diagram</strong>
                    <button type="button" class="mermaid-modal__close" aria-label="Close expanded diagram">Close</button>
                </div>
                <div class="mermaid-modal__content"></div>
            </div>
        `;

        modal.addEventListener('click', (event) => {
            const target = event.target;
            if (!(target instanceof HTMLElement)) {
                return;
            }

            if (target.dataset.mermaidClose === 'true' || target.classList.contains('mermaid-modal__close')) {
                closeMermaidModal();
            }
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeMermaidModal();
            }
        });

        document.body.appendChild(modal);
        return modal;
    };

    const enhanceMermaidDiagrams = () => {
        ensureMermaidModal();

        for (const diagram of document.querySelectorAll('pre.mermaid')) {
            const svg = diagram.querySelector('svg');
            if (!svg) {
                continue;
            }

            if (!diagram.querySelector('.mermaid-expand-button')) {
                const expandButton = document.createElement('button');
                expandButton.type = 'button';
                expandButton.className = 'mermaid-expand-button';
                expandButton.setAttribute('aria-label', 'Expand diagram');
                expandButton.innerHTML = maximizeIcon;
                expandButton.addEventListener('click', (event) => {
                    event.stopPropagation();
                    openMermaidModal(diagram);
                });

                diagram.appendChild(expandButton);
            }

            diagram.dataset.mermaidEnhanced = 'true';
        }
    };

    const observeMermaidDiagrams = () => {
        const observer = new MutationObserver(() => enhanceMermaidDiagrams());
        observer.observe(document.body, { childList: true, subtree: true });

        window.addEventListener('load', enhanceMermaidDiagrams, { once: true });
        setTimeout(enhanceMermaidDiagrams, 250);
        setTimeout(enhanceMermaidDiagrams, 1000);
    };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            enhanceMermaidDiagrams();
            observeMermaidDiagrams();
        }, { once: true });
    } else {
        enhanceMermaidDiagrams();
        observeMermaidDiagrams();
    }

    // Simplest way to make mermaid re-render the diagrams in the new theme is via refreshing the page

    for (const darkTheme of darkThemes) {
        const button = getThemeButton(darkTheme);
        button?.addEventListener('click', () => {
            if (lastThemeWasLight) {
                window.location.reload();
            }
        });
    }

    for (const lightTheme of lightThemes) {
        const button = getThemeButton(lightTheme);
        button?.addEventListener('click', () => {
            if (!lastThemeWasLight) {
                window.location.reload();
            }
        });
    }
})();
