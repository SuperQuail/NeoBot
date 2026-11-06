# Change records

Every user-visible change needs one Markdown file in this directory.

Example record:

    ---
    type: feat
    scope: cache
    packages:
      npm@my-package: minor
    ---

    Describe the change in one or two sentences.

Fields:

- type: feat, fix, perf, docs, refactor, test, build, ci, chore, style or revert
- scope: optional area name
- packages: package name to bump level (patch, minor, major)
- release: optional, defaults to true; false records only appear in the changelog

Create records with qegg commit.
