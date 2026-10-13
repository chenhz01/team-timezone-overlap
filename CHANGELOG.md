# Changelog

All notable changes to this project are documented here.
Format inspired by Keep a Changelog; versions are 0.x while the tool stabilizes.

## [0.1.1] - 2026-10-13

### Changed
- Second-round revision after a full self-audit (rules 85-100 alignment pass):
  fairness rotation covered by a 3-member fragmented-coverage fixture; 23:59-end granularity behavior documented and tested; offset parser table (+05:30, Z, -03:30, boundaries) added; comfort-boundary edge cases tested

### Fixed
- Self-test suite hardened to 64 cases across three classes
  (functional / error-path / extreme-edge); final run `SUMMARY: PASS 64/64`.

## [0.1.0] - 2026-10-13

### Added
- Initial release: pure-stdlib core, argparse CLI, three-tier finding model,
  text and JSON output, and an article-level README with measured
  performance, Minimal Fallback, Design Trade-offs, Limits & Second-order
  Effects, FAQ, and Core Assumptions.
