# ChaCha DEV checkpoint — 2026-09-25 — V7.8 runtime acquired / V7.9 migration ready

## Current acquired runtime

- Platform version: **7.8.0**
- Active runtime revision: **a3d2a55b3652db8934d0b125f094efabe9e0e2e5**
- Active release path: `/opt/chacha-dev/platform/releases/20260925T082245Z-a3d2a55b3652db8934d0b125f094efabe9e0e2e5`
- Direct Operator service: **active**
- Direct Operator bind: `127.0.0.1:8792`
- Private Tailscale surface: **8443 -> 127.0.0.1:8792**
- Public Radar Funnel preserved: **443 -> 127.0.0.1:8788**
- Native Update private surface preserved: **8445 -> /opt/chacha-dev/runtime/native-update/current/packages**
- Guardian heartbeat timer: **active**
- Physical retained releases: **3**

Runtime evidence:
- `/opt/chacha-dev/evidence/v780-runtime-convergence-20260925T082245Z.json`
- Final installer log: `/tmp/chacha-v780-deploy-a3d2a55b3652db8934d0b125f094efabe9e0e2e5/install.log`

## V7.8 acquisition result

Final installer result:

- `CHACHA_DEV_V780_INSTALL=PASS`
- `CHACHA_DEV_V780_DIRECT_OPERATOR=PASS`
- `CHACHA_DEV_V780_PRIVATE_TAILSCALE_SERVE=PASS`
- `CHACHA_DEV_V780_REAL_DIRECT_STATUS=PASS`
- `CHACHA_DEV_V780_REAL_FUNCTIONAL_TRANSLATION=PASS`
- `CHACHA_DEV_V780_LIVE_UPDATE=PASS`
- `CHACHA_DEV_V780_NATIVE_UPDATE=PASS`
- `CHACHA_DEV_V780_OBJECT_FACTORY=PASS`
- Guardian coverage: **55/55 PASS / INFO**
- Guardian D1 sync: **DIGEST_AWARE_DELTA**
- Automatic external spend: **0 EUR**

The first V7.8 attempt on `76befbe0...` correctly rolled back because the Direct Operator systemd sandbox did not allow scoped project-assurance key creation.

Corrective commits:
- `9d0b292fc4a007d1cb42f81121126b469d26d94e` — permit scoped project-assurance key writes
- `a3d2a55b3652db8934d0b125f094efabe9e0e2e5` — create scoped project-assurance secret directory

After correction, the second deployment completed successfully.

## V7.8 exact-SHA assurance

Branch: `dev-hub-v780-runtime-convergence`

The acquired runtime revision `a3d2a55b...` inherits the fully qualified V7.8 chain. Before deployment, the candidate passed:
- V7.8 runtime convergence qualification
- V7 platform qualification
- Sentinel technical assurance
- Guardian coverage sync

Guardian external coverage was synchronized to **55 components** before activation.

## Progress / Live UI / Native Update

Persistent progress:
- Global ChaCha DEV maturity remains distinct from active work progress.
- Current global maturity reference: **86%**
- Shared progress source is exposed through Direct Operator.

Live Update:
- UI/configuration can be updated remotely through ChaCha DEV without rebuilding the APK for normal UI/behavior changes.
- Live UI publisher is atomic and rollbackable.
- Live UI has no native APK install authority.

Native Update:
- Permanent release signing certificate SHA-256:
  `3a39f13de1191aec28526d5d8e7c9b490723d514b8dd87e5cb30aaa86a6bff88`
- Private key remains VPS-only under `/opt/chacha-dev/secrets/android/`.
- Native shell release **0.6.0 / versionCode 6** is signed and published privately.
- Signed APK SHA-256:
  `b5088f795fb2e3f2ab63b77c24df67e22986f0cfe9a782592a4ec64e9fa7428e`
- Current native update release:
  `/opt/chacha-dev/runtime/native-update/releases/20260924T220201Z-200cbe417be3-v0.6.0`
- Android user confirmation remains mandatory.
- Silent installation remains forbidden.

## V7.9 Android migration bootstrap

Branch: `dev-hub-v790-android-migration-bootstrap`

Qualified revision:
- **dace99b448c7e9773a626191d2d63a1486d996ed**

Exact-SHA gates:
- ChaCha DEV V7.9 Android migration bootstrap: **SUCCESS**
- ChaCha DEV Sentinel technical assurance: **SUCCESS**
- ChaCha DEV V7 platform qualification: **SUCCESS**

Built artifact:
- Name: `chacha-migration-v790-debug`
- Artifact id: `10837381270`
- Size: `876908` bytes
- Artifact digest: `sha256:42f6bfe721e9f49695b2a1faeabaeb5f13d59f9afe489eb0688668587fff5d26`

Migration flow:
1. Install/open temporary `ChaCha Migration` app.
2. Detect current `com.wfgg.chachadev.operator` signature.
3. Only if the legacy/debug identity is installed, request Android-confirmed uninstall.
4. Download ChaCha 0.6.0 from the private Tailscale native-update channel.
5. Verify APK SHA-256, package id, version code/name, and pinned signing certificate.
6. Launch Android-confirmed install of the permanent release identity.
7. Offer removal of the temporary migration app.

Do not attempt silent uninstall/install. Android confirmations are intentional.

## Object Factory

V7.7 Object Factory is part of the acquired V7.8 runtime.

Responsibility chain:
`Project Intent -> Project Planner / Dev Architect -> Object Factory -> Component Factory -> Capability Foundry only on technical gap -> Guardian/Sentinel`

Rules:
- Reuse qualified objects before build.
- Data-storing apps without an explicit object model block code generation with `OBJECT_MODEL`.
- Object Factory owns object contracts, not production provider selection or direct database mutation.
- Object Factory is registered in Capability Registry, Guardian, Technology Watch and universal evolution governance.

## Resume point

Do **not** replay V7.3–V7.8 development or deployment.

Next work should start from:
1. **V7.8 runtime already acquired and active at a3d2a55b...**
2. **V7.9 migration bootstrap already qualified at dace99b4...**
3. Retrieve/deliver the V7.9 migration APK to the user if not already delivered.
4. Guide the one-time migration from the old debug-signed ChaCha app to permanent signed release 0.6.0.
5. After migration, verify the installed certificate/version and that the private Live Update UI / widget still work.
6. Then continue normal ChaCha DEV work from V7.8; future ordinary UI changes should use Live Update rather than a new APK.

