---
name: False positive report
about: Report a diagnostic ID that code-harness reports wrongly for a valid construct
title: "False positive: <diagnostic ID> (<language>)"
---

## Diagnostic

- Diagnostic ID: `<rule>` (the `rule` field of the report)
- Language / analyzer: <language>
- Severity: <error or warning>

## Environment

- Installation: <how code-harness was installed>
- Version: <version visible from that installation, or "unknown">
- OS: <operating system and version>
- Scanned source language / runtime: <language and runtime version>

## Command line

```sh
code-harness --root <root> --config <policy-path> --all --format text
```

## Policy (`.codeharness/code-harness.json`)

```json
{}
```

## Minimal reproduction

Layout:

```
<repro>/
  .codeharness/code-harness.json
  sample.py
```

Policy `.codeharness/code-harness.json`:

```json
{}
```

`sample.py`:

```python
def add(left, right):
    return left + right
```

Command:

```sh
code-harness --root <repro> --all --format text
```

Expected behavior: <what the correct result is — for a false positive that
usually means no finding is reported here — and why>

Actual output:

```
<paste the full text output of the reproduction run, line for line>
```

## Scale in the original project

- Findings for this diagnostic ID: <N>
- Files involved: <M>
- Sample paths: <path>, <path>, <path>

## Why this looks like a false positive

<the code semantics, what the checker appears to assume, and where the two
diverge>

## Workarounds tried (optional)

<what was attempted and why it is not an acceptable resolution>
