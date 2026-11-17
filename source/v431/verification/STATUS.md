Independent Batocera 43.1 image verifier is running against the eMMC image.

- Frozen primary rootfs: 23 critical/preserved/adapted files, 1024 kernel module tree entries, 1 removed donor path independently pinned.
- Official secondary SquashFS: full decompression, unchanged official hash, 103 AArch64 libretro cores and required platform core paths all pass.
- Official 43.1 initrd: original init hash, primary:secondary overlay precedence, static AArch64 BusyBox and absence of kernel modules checked.
- Verifier fixtures: 17/17 PASS. Assembly review: 11/11 PASS.
- Full eMMC verification running; installer validation awaits final assembled/gzipped image.

Found an installer default filename bug (old batocera40 filename in 43.1 script while docs use default); root notified in shared upstream-status.md. Verifier now checks the AST default matches the actual 43.1 payload name.
