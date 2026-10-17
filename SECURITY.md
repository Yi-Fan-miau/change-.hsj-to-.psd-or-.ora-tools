# Security Policy

## Reporting

Please do not open a public issue for security-sensitive problems.
Use GitHub's private vulnerability reporting / Security Advisories for this
repository, or contact the maintainer through the profile contact link.

Include: affected version, platform (Windows/Android), a minimal reproduction,
and the potential impact. Do not include personal drafts or third-party
copyrighted files.

## Scope

- The converter processes untrusted `.hsj` files locally. Parser bounds,
  decompression limits, and path handling are in scope.
- The Android app uses SAF and does not request broad storage permissions.
- Signing keys and generated binaries are not stored in the repository.
- The project does not bypass DRM, licensing, or access controls.
