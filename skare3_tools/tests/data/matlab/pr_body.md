# ska3-matlab 2026.13

This PR includes:
- fot-matlab: Adds a kadi-based, ORV-compatible starting configuration generator, and uses SCS-85 for the HRC 2S2ONST state.
- kadi:
  - Events database updates no longer cause NFS issues.
  - Add function `get_observation` to get a single observation.
- cheta: ACA L0 image telemetry is now available from the cheta archive ([cheta#291](https://github.com/sot/cheta/pull/291)).

## Interface Impacts:

### Data products to be promoted to `$SKA/data`

None for this release.

<details>
<summary>Notes on judgement</summary>

Of the 19 PRs in the code changes, only three filled in an interface-impacts section.

</details>

## Testing:

- [Automated tests](https://icxc.cfa.harvard.edu/aspect/skare3/testr/releases/2026.13/).

```
conda create -n ska3-matlab-2026.13rc# --override-channels \
  -c https://icxc.cfa.harvard.edu/aspect/ska3-conda/flight \
  ska3-matlab==2026.13rc#
```

## Review

All operations critical or impacting PR's are independently and carefully reviewed.

# Code changes

## ska3-matlab (2026.10 -> 2026.13rc1)

- **kadi:** 7.22.0 -> 7.23.0 (7.22.0 -> 7.23.0)
  - [PR 388](https://github.com/sot/kadi/pull/388) (Javier Gonzalez): close stale connections

# Related Issues

Fixes #1730
