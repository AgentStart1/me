# PvgTimingFix

This independent Lilu plugin publishes AppleParavirtFramebuffer's existing
fixed-rate detailed timing. It prevents virtual-machine scheduling jitter from
becoming the nominal display period used by CoreVideo. It does not implement
video decoding or replace application presentation commands.

The included `PvgTimingFix` is the qualified x86-64 Mach-O kext bundle.
`artifact.json` records its checksum, source files and dependency revisions.
The driver only routes the audited 52-byte method on Darwin 24; a different
method remains untouched. Packaging requires macOS 15.8.1 build **24H32** and
Lilu **1.7.2**. Other versions, display-mode changes and sleep/resume are not
qualified. `-pvgtimingoff` disables the plugin.

Keep firmware, private credentials and VM state outside consuming projects.
Prepare a new copy of an operator-owned OpenCore image with the plugin's
`prepare-macos-gpu-boot.py`; see the plugin README. Neither the system volume
nor the supplied original firmware is modified.

For contributor rebuilds and qualification, see the plugin DEVELOPMENT.md.
Lilu's applicable source/binary redistribution terms are retained in
`LICENSE-Lilu.txt`. The new timing hook is distributed under `LICENSE`.
