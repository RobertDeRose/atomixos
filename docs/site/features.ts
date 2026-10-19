import fs from 'node:fs';
import path from 'node:path';

// A feature is delivered once its directory has an implemented record (index.md). Only delivered features are
// published; directories without one, and underscore-prefixed templates, stay out of the site.
const featuresDir = path.join(__dirname, '..', 'src', 'features');

function featureDirectories(): string[] {
  return fs
    .readdirSync(featuresDir, {withFileTypes: true})
    .filter((entry) => entry.isDirectory() && !entry.name.startsWith('_'))
    .map((entry) => entry.name);
}

const isDelivered = (slug: string): boolean => fs.existsSync(path.join(featuresDir, slug, 'index.md'));

export function deliveredFeatures(): {slug: string; title: string}[] {
  return featureDirectories()
    .filter(isDelivered)
    .map((slug) => {
      const source = fs.readFileSync(path.join(featuresDir, slug, 'index.md'), 'utf8');
      return {slug, title: source.match(/^# (.+)$/m)?.[1] ?? slug};
    })
    .sort((a, b) => a.title.localeCompare(b.title));
}

// Docs-plugin exclude globs, relative to src/, for features that are not delivered yet.
export function undeliveredFeatureGlobs(): string[] {
  return featureDirectories()
    .filter((slug) => !isDelivered(slug))
    .map((slug) => `features/${slug}/**`);
}
