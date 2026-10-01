# ska3-flight 2026.9

This PR includes mostly changes useful for aspect. The more important ones are:
- cheta: Support ingesting ACA L0 image telemetry into cheta archive
- mica: Support decom of the 32-bit HDR3 quadrant offsets

## Interface Impacts:

This release requires the cheta ACA image telemetry data from sot/cheta/pull/291. This was copied into `$SKA/data/eng_archive` **in the test environment** and will need to be promoted to the flight environment. This is accounted for in the ska3-flight issue (#1708)

## Testing:

- [HEAD](https://icxc.cfa.harvard.edu/aspect/skare3/testr/releases/2026.9rc3-HEAD/).
- [GRETA](https://icxc.cfa.harvard.edu/aspect/skare3/testr/releases/2026.9rc3-GRETA/) (on chimchim).

The latest release candidates will be installed in `/proj/sot/ska3/test` on HEAD, and all release candidates will be available for testing from the usual channels:
```
conda create -n ska3-flight-2026.9rc3 --override-channels \
  -c https://icxc.cfa.harvard.edu/aspect/ska3-conda/flight \
  -c https://icxc.cfa.harvard.edu/aspect/ska3-conda/test \
  ska3-flight==2026.9rc3
```

## Review

All operations critical or impacting PR's are independently and carefully reviewed. For other PR's the level of detail for review is calibrated to operations criticality.

## Deployment

ska3-flight 2026.9 will be promoted to flight conda channel and installed on HEAD and GRETA Linux upon approval of FSDS Jira ticket.

# Code changes

## ska3-flight changes (2026.6 -> 2026.9rc3)

### Updated Packages

- **aca_view:** 0.18.0 -> 0.19.0 (0.18.0 -> 0.19.0)
  - [PR 217](https://github.com/sot/aca_view/pull/217) (Javier Gonzalez): When fetching data from mica l0 files, set AABGDTYP from the files
