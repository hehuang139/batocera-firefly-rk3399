# FROZEN

Final rootfs has 15 pinned file rules and the complete 841-file Linux 6.6.27 BSP module tree. All seven validation groups pass. The 43.1 version, 304-entry default controller database and executable/library invariants remain pinned.

Host-generated Select Python bytecode removed from overlay, provenance and image. Helper imports disable bytecode creation. Serial getty uses ttyS2 at 1500000 baud. HDMI tty5 remains the upstream configuration. No further rootfs changes planned.

- provenance.json: `5f73a8da7330c11171d9095a901c38da1e4e12c904b38cb9536b0f6cc7f937bc`
- adaptation.json: `21ed01a00870833ddfc9b253bea38b3e7498c86ea2f17e0bd958c544ccb34f9a`
- validation.json: `52d6fefcd37b7240ba77cc17a003c10aba418c3c6d6878337b8a48d0ada4dfdc`
