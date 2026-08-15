# PR: bounded corporate-site contact crawl

## Summary

Adds an isolated “corporate site contact crawl” behind the existing
`WebCrawler` adapter. After a domínio corporativo defensável exists,
`CompanyWebsiteProvider` seeds homepage + #392/#394 useful URLs + sitemap +
robots + internal links, scores high-value paths, and extracts
pessoa/cargo/email only from structural evidence.

Does **not** rewrite #392 domain resolution, query planner, or SearXNG/DDGS.
Does **not** touch Warmbly, web-cfg, or SmartLic.

## Budget defaults

| Limit | Default |
|---|---|
| pages | 12 |
| depth | 3 |
| bytes | 2_500_000 |
| time | 20s |
| redirects | 5 |
| requests/min | 20 |
| sitemap locs parsed | 80 |

## SITE_* contract

Strong: `SITE_PROFILE_EMAIL`, `SITE_TEAM_CARD_EMAIL`, `SITE_MAILTO_ASSOCIATED`,
`SITE_STRUCTURED_CONTACT`.

Never a person: `SITE_GENERIC_ONLY`, `SITE_JS_BLOCKED`,
`SITE_NO_HIGH_VALUE_PATH`, `SITE_STALE_OR_UNKNOWN`.

Weak proximity / cross-card mailto / holding domain stay candidate.

## Tests

Adversarial fixtures cover correct/incorrect mailto, two nearby staff, footer
genérico, individual profile, JSON-LD coherent vs incoherent, obfuscation,
holding, huge sitemap, external redirect, login/cart/search skip-list.

CLI `site-crawl --fixture` is the shipped local launch path.

## Canary

Live TRACK_A 30 needs SearXNG/DDGS. When those are down, fixture before/after
is the recorded evidence: +5 named-associated, 0 footer promotions, 0
proximity promotions.

## Recommendation

Ship the isolated layer. Keep the defaults. Run live 30 when #394 is up.
Do not open a generic spider.
