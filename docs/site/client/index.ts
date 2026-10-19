import ExecutionEnvironment from '@docusaurus/ExecutionEnvironment';
import '@fontsource-variable/exo-2';
import '@fontsource-variable/atkinson-hyperlegible-next';
import '@fontsource-variable/atkinson-hyperlegible-mono';

// On narrow screens, diagrams scroll rather than scale below this fraction of their natural size,
// which keeps Mermaid's 16px labels at about 10px.
const DIAGRAM_MIN_SCALE = 0.65;
const ZOOM_STEP = 0.25;
const ZOOM_MIN = 0.5;
const ZOOM_MAX = 4;

let dialog: HTMLDialogElement | null = null;
let zoom = 1;

function button(label: string, text: string, onClick: () => void): HTMLButtonElement {
  const el = document.createElement('button');
  el.type = 'button';
  el.className = 'atomixos-diagram-control';
  el.setAttribute('aria-label', label);
  el.textContent = text;
  el.addEventListener('click', onClick);
  return el;
}

function applyZoom(): void {
  const svg = dialog?.querySelector<SVGSVGElement>('.atomixos-diagram-dialog__canvas svg');
  if (!svg) return;
  const width = svg.viewBox.baseVal?.width || svg.getBoundingClientRect().width;
  svg.style.width = `${width * zoom}px`;
  svg.style.maxWidth = 'none';
  svg.style.height = 'auto';
}

function setZoom(next: number): void {
  zoom = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));
  applyZoom();
}

// One shared dialog shows an enlarged copy of whichever diagram was expanded.
function ensureDialog(): HTMLDialogElement {
  if (dialog) return dialog;
  dialog = document.createElement('dialog');
  dialog.className = 'atomixos-diagram-dialog';
  dialog.setAttribute('aria-label', 'Expanded diagram');
  const toolbar = document.createElement('div');
  toolbar.className = 'atomixos-diagram-dialog__toolbar';
  toolbar.append(
    button('Zoom out', '−', () => setZoom(zoom - ZOOM_STEP)),
    button('Reset zoom', '100%', () => setZoom(1)),
    button('Zoom in', '+', () => setZoom(zoom + ZOOM_STEP)),
    button('Close diagram', 'Close', () => dialog?.close()),
  );
  const canvas = document.createElement('div');
  canvas.className = 'atomixos-diagram-dialog__canvas';
  dialog.append(toolbar, canvas);
  // Drop the copy on close so its duplicate IDs and scoped styles don't linger.
  dialog.addEventListener('close', () => canvas.replaceChildren());
  dialog.addEventListener('click', (event) => {
    if (event.target === dialog) dialog?.close();
  });
  document.body.append(dialog);
  return dialog;
}

function expand(container: Element): void {
  const svg = container.querySelector('svg');
  if (!svg) return;
  const target = ensureDialog();
  const canvas = target.querySelector('.atomixos-diagram-dialog__canvas')!;
  // The copy keeps its ID and classes so Mermaid's scoped styles and the brand styles apply.
  const copy = svg.cloneNode(true) as SVGSVGElement;
  const wrapper = document.createElement('div');
  wrapper.className = 'docusaurus-mermaid-container';
  wrapper.append(copy);
  canvas.replaceChildren(wrapper);
  zoom = 1;
  target.showModal();
  applyZoom();
}

function enhance(): void {
  document.querySelectorAll('.docusaurus-mermaid-container').forEach((container) => {
    if (container.closest('.atomixos-diagram-dialog') || !container.querySelector('svg')) return;
    if (container.querySelector('.atomixos-diagram-expand')) return;
    const svg = container.querySelector<SVGSVGElement>('svg')!;
    const naturalWidth = svg.viewBox.baseVal?.width;
    if (naturalWidth) svg.style.setProperty('--atomixos-diagram-min-width', `${naturalWidth * DIAGRAM_MIN_SCALE}px`);
    const expandButton = button('Expand diagram', 'Expand', () => expand(container));
    expandButton.classList.add('atomixos-diagram-expand');
    container.append(expandButton);
  });
}

// Mermaid renders after navigation, so watch for diagrams as they appear.
if (ExecutionEnvironment.canUseDOM) {
  new MutationObserver(enhance).observe(document.body, {childList: true, subtree: true});
}
