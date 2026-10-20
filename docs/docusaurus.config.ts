import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';
import {themes as prismThemes} from 'prism-react-renderer';
import {GlobExcludeDefault} from '@docusaurus/utils';
import {undeliveredFeatureGlobs} from './site/features';

const repoUrl = 'https://github.com/RobertDeRose/atomixos';

// The product page (product/ at the repository root) owns the Pages root; the docs live under docs/.
const siteBaseUrl = '/atomixos/';
const baseUrl = `${siteBaseUrl}docs/`;
// Docusaurus prefixes baseUrl to root-relative links, so the product page is baseUrl's parent; pathname:// keeps it a
// plain link instead of a client-side route.
const productPageHref = `pathname://${baseUrl}../`;

const config: Config = {
  title: 'AtomixOS',
  tagline: 'The element of reproducibility',
  // The SVG stays crisp at tab size; the PNG is the fallback for browsers without SVG favicons.
  favicon: 'img/atomixos-favicon.svg',
  headTags: [
    {tagName: 'link', attributes: {rel: 'icon', type: 'image/png', sizes: '64x64', href: `${baseUrl}img/atomixos-favicon.png`}},
  ],
  url: 'https://robertderose.github.io',
  baseUrl,
  trailingSlash: false,
  // The product page reads the same localStorage key, so the color mode carries between the two.
  storage: {type: 'localStorage', namespace: false},

  // Rspack's persistent cache is off because concurrent builds (docs:serve plus the hk docs step)
  // corrupt it and crash Rspack.
  future: {
    faster: {
      swcJsLoader: true,
      swcJsMinimizer: true,
      swcHtmlMinimizer: true,
      lightningCssMinimizer: true,
      mdxCrossCompilerCache: true,
      rspackBundler: true,
      rspackPersistentCache: false,
      ssgWorkerThreads: true,
      gitEagerVcs: true,
    },
    v4: {removeLegacyPostBuildHeadAttribute: true},
  },

  onBrokenLinks: 'throw',
  onBrokenAnchors: 'throw',

  markdown: {
    // .md pages are CommonMark; only .mdx pages are parsed as MDX.
    format: 'detect',
    mermaid: true,
    hooks: {
      onBrokenMarkdownLinks: 'throw',
      onBrokenMarkdownImages: 'throw',
    },
  },
  themes: [
    '@docusaurus/theme-mermaid',
    [
      '@easyops-cn/docusaurus-search-local',
      {hashed: true, docsDir: 'src', docsRouteBasePath: '/', indexBlog: false, indexPages: false},
    ],
  ],

  // Site code lives in site/ because src/ is the documentation content.
  staticDirectories: ['site/static'],
  clientModules: ['./site/client/index.ts'],

  presets: [
    [
      'classic',
      {
        docs: {
          path: 'src',
          routeBasePath: '/',
          sidebarPath: './sidebars.ts',
          // Only delivered behavior is published: undelivered feature designs and the roadmap stay in the repository.
          exclude: [...GlobExcludeDefault, 'planned-features.md', ...undeliveredFeatureGlobs()],
          editUrl: `${repoUrl}/edit/dev/docs/`,
        },
        blog: false,
        pages: {path: 'site/pages'},
        theme: {customCss: './site/css/custom.css'},
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {respectPrefersColorScheme: true},
    // Brand colors are applied in site/css/custom.css; base themes keep Mermaid's palette neutral.
    // Mermaid sizes boxes with this font, so it must match the site's body font.
    mermaid: {
      theme: {light: 'neutral', dark: 'dark'},
      options: {
        fontFamily: "'Atkinson Hyperlegible Next Variable', sans-serif",
        themeVariables: {fontFamily: "'Atkinson Hyperlegible Next Variable', sans-serif"},
      },
    },
    navbar: {
      title: 'AtomixOS',
      logo: {alt: 'AtomixOS logo', src: 'img/atomixos-icon.png', href: productPageHref, target: '_self'},
      items: [
        {to: '/', label: 'Docs', position: 'left', activeBaseRegex: '.*'},
        {href: repoUrl, label: 'GitHub', position: 'right'},
      ],
    },
    docs: {sidebar: {hideable: true}},
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['nix', 'bash', 'toml', 'json', 'ini', 'docker'],
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
