# Ska package builder

A github action to build ska packages

## Inputs

### `package`

**Required** The name of the package to build.

## Outputs

### `files`

The files just built.

## Example usage

uses: sot/actions/build@v1
with:
  package: 'Quaternion'