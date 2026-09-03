# Pose V6.8 model and licence gate

Review date: 2026-09-01.

## SAM 2.1 silhouette expert

- Upstream: `facebookresearch/sam2`.
- Pinned source revision: `2b90b9f5ceec907a1c18123530e92e794ad901a4`.
- Code/checkpoint licence: Apache-2.0.
- Production decision: `PRODUCTION_APPROVED` for the silhouette-only role.
- ACCURATE checkpoint: `sam2.1_hiera_base_plus.pt`, 323,606,802 bytes,
  SHA-256 `a2345aede8715ab1d5d31b4a509fb160c5a4af1970f199d9054ccfb746c004c5`.
- ULTRA checkpoint: `sam2.1_hiera_large.pt`, 898,083,611 bytes,
  SHA-256 `2647878d5dfa5098f2f8649825738a9345572bae2d4350a2468587ece47dd318`.

The production worker never downloads these artifacts. The pinned installer
performs size and SHA-256 verification. SAM2 identifies the visible region of
the already locked person and is not a joint measurement.

## SAM 3D Body geometry referee

- Upstream: `facebookresearch/sam-3d-body`.
- Official checkpoints considered: `facebook/sam-3d-body-dinov3` and
  `facebook/sam-3d-body-vith`.
- Code and checkpoints: SAM License, last updated 2025-11-19.
- Checkpoints: gated Hugging Face access; separate acceptance/authentication is
  required and the MHR body asset is bundled with the gated material.
- Dependency surface includes Detectron2 and a separate large PyTorch stack.
- V6.8 decision: `BENCHMARK_ONLY`.

No checkpoint was copied to the repository and no runtime was enabled. Legal
approval of the SAM License, checkpoint access, dependency licences and the
intended commercial deployment is required before production enablement.
Even if approved later, monocular mesh output may only arbitrate topology and
orientation. It must not be represented as metrological 3D, calibrated body
dimensions, or a measured ergonomic angle.

## Additional 2D pose challenger

No additional pose model is enabled. RTMW and TAR already provide independent
image evidence, while TAP provides trajectory evidence. A ViTPose-H/DWPose
challenger requires an official-weight, licence-reviewed worst-frame benchmark
that demonstrates material value before it may enter production.
