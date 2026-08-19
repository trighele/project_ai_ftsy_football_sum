# 06 — Build the stylesheet on Windows

**What to build:** A prefactor. The stylesheet build script branches on Linux and macOS and exits on anything else, so on the maintainer's machine the compiled stylesheet cannot be rebuilt at all — every styling change is blocked behind it. The script learns to recognise the Git Bash / MSYS environment and fetch the Windows build of the standalone Tailwind CLI.

Nothing about the application changes. The proof is that running it produces the committed stylesheet unchanged.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

See [../spec.md](../spec.md).

- [ ] The script runs to completion in Git Bash on Windows and writes the stylesheet
- [ ] Running it with no source changes leaves the committed stylesheet byte-identical
- [ ] The Linux and macOS paths are unchanged
- [ ] The downloaded binary still lands in the ignored tools directory and is not committed
