import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';
import {deliveredFeatures} from './site/features';

type SidebarItemConfig = Extract<SidebarsConfig[string], unknown[]>[number];

const doc = (id: string, label: string): SidebarItemConfig => ({type: 'doc', id, label});

const category = (
  label: string,
  items: SidebarItemConfig[],
  options: {link?: string; collapsed?: boolean} = {},
): SidebarItemConfig => ({
  type: 'category',
  label,
  collapsed: options.collapsed ?? true,
  ...(options.link ? {link: {type: 'doc', id: options.link}} : {}),
  items,
});

// Implemented features are listed from their delivered records, so only completed work appears. A feature's design
// record is linked from its implemented record rather than listed here.
const implementedFeatures = (): SidebarItemConfig[] =>
  deliveredFeatures().map(({slug, title}) => doc(`features/${slug}/index`, title));

// Navigation for docs/src, grouped by reader intent. Register every new durable page here.
const sidebars: SidebarsConfig = {
  docs: [
    doc('README', 'Introduction'),
    category(
      'Architecture',
      [
        doc('architecture/partition-layout', 'Partition Layout'),
        doc('architecture/update-rollback', 'Update and Rollback'),
        doc('architecture/network-topology', 'Network Topology'),
        doc('architecture/authentication', 'Authentication'),
        doc('architecture/nixstasis-enrollment', 'Nixstasis Enrollment'),
        doc('data-flow', 'Data Flow'),
        doc('runtime-boundaries', 'Runtime Boundaries'),
        doc('design-decisions', 'Design Decisions'),
      ],
      {link: 'architecture', collapsed: false},
    ),
    category(
      'Operations',
      [
        doc('provisioning/flash-image', 'Flash an Image'),
        doc('cm3', 'Radxa CM3 IO Board'),
        doc('provisioning/lan-range', 'LAN Range'),
        doc('provisioning/fleet-bootstrap', 'Fleet Bootstrap'),
        doc('operations/ntp-settings', 'NTP Settings'),
        doc('tutorials/oidc-device-management', 'OIDC Device Management'),
      ],
      {link: 'provisioning'},
    ),
    category(
      'Development',
      [
        doc('testing', 'Testing'),
        doc('hardware-testing', 'Hardware Testing'),
        doc('development/adding-board-support', 'Adding Board Support'),
        doc('development/tooling', 'Developer Tooling'),
        doc('development/releasing', 'Releasing'),
        doc('development/feature-lifecycle', 'Feature Lifecycle'),
        doc('development/documentation-conventions', 'Documentation Conventions'),
        doc('development/github-pages', 'GitHub Pages Deployment'),
      ],
      {link: 'building'},
    ),
    category(
      'Reference',
      [
        doc('reference/build-configuration', 'Build Configuration'),
        doc('reference/flake-outputs', 'Flake Outputs'),
        doc('reference/project-structure', 'Project Structure'),
        category(
          'Code Reference',
          [
            doc('code-reference/modules', 'NixOS Modules'),
            doc('code-reference/derivations', 'Nix Derivations'),
            doc('code-reference/scripts', 'Scripts'),
          ],
          {link: 'code-reference'},
        ),
        category('Platform Specifications', [
          doc('specs/nix-flake-config', 'Nix Flake Configuration'),
          doc('specs/partition-layout', 'Partition Layout'),
          doc('specs/rauc-integration', 'RAUC Integration'),
          doc('specs/boot-rollback', 'Boot and Rollback'),
          doc('specs/watchdog', 'Watchdog'),
          doc('specs/update-confirmation', 'Update Confirmation'),
          doc('specs/lan-gateway', 'LAN Gateway'),
        ]),
      ],
      {collapsed: false},
    ),
    category('Implemented Features', implementedFeatures(), {link: 'features/index'}),
  ],
};

export default sidebars;
