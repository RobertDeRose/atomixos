#!/usr/bin/env bash
# Promote the validated commit and its annotated tag together, without rewriting history.
set -euo pipefail

if [[ $# != 2 || ! $1 =~ ^[0-9a-f]{40}$ || ! $2 =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
	echo "Usage: release-refs.sh <validated-commit-sha> <vX.Y.Z>" >&2
	exit 1
fi
sha=$1
tag=$2
test "$(git rev-parse "$sha^{commit}")" = "$sha"

# Query once so a network failure cannot be mistaken for an absent branch or tag.
refs=$(git ls-remote --refs origin refs/heads/main "refs/tags/$tag")
tag_object=
while read -r object ref; do
	case "$ref" in
	refs/heads/main)
		git fetch --no-tags origin "$object"
		if ! git merge-base --is-ancestor "$object" "$sha"; then
			echo "ERROR: main is not an ancestor of the validated release commit" >&2
			exit 1
		fi
		;;
	"refs/tags/$tag")
		git fetch --no-tags origin "$object"
		if [[ $(git rev-parse "$object^{commit}") != "$sha" ]]; then
			echo "ERROR: $tag already identifies a different commit" >&2
			exit 1
		fi
		tag_object=$object
		;;
	esac
done <<<"$refs"

if [[ -z $tag_object ]]; then
	git tag -a "$tag" -m "release: $tag" "$sha"
	tag_object=$(git rev-parse "refs/tags/$tag")
fi

# No force: Git rejects a non-fast-forward main or a changed tag. Atomic publication
# also leaves both remote refs untouched if either update is rejected by a ruleset.
git -c push.followTags=false push --atomic origin "$sha:refs/heads/main" "$tag_object:refs/tags/$tag"
