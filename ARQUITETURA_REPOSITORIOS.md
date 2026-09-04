# ARQUITETURA_REPOSITORIOS — where the product/client line sits

Referenced from `docs/plugins.md`, `TODO.md`, and `mebuska-deploy/paqtcpb/dados.py`
as the document that explains where the boundary between "product" and
"client-specific" sits. It didn't exist until now — this fixes that.

Status: draft, written from repo inspection on 2026-09-03. Supersedes nothing;
formalizes decisions that were previously only implicit in `TODO.md` and in
the shape of `mebuska-deploy`. Needs review from whoever owns the PaqTcPB
relationship before being treated as settled, particularly §2.

---

## 1. Why this document exists

`corporate-backend` was created on 2026-08-03 as a full copy of
`municipal-backend` (via `git archive`, which carries no commit history) instead
of an extracted shared module. That was a deliberate choice, driven by an
unresolved IP clause in the PaqTcPB Plano de Trabalho (see §2) — not a
technical preference. It was never written down as an architecture decision,
which is how three different docs ended up pointing at a file that didn't
exist. This is that file.

## 2. IP ownership — the split this architecture is built around

The Plano de Trabalho does not define IP ownership, and its language ("fortalece
**seu** portfólio", "um núcleo algorítmico inteiramente novo") points toward the
Foundation, not BusKá. The working split, pending a signed amendment:

| IP class | Owner | What's in it |
|---|---|---|
| **Background IP** | BusKá | `municipal-backend` and anything generalized from it: auth, RBAC, tenancy, geo primitives, notifications, error handling, the plugin-discovery mechanism itself |
| **Foreground IP** | PaqTcPB | Work built specifically for this contract: trip lifecycle state machine, capacity engine, buffer window, dynamic QR boarding, offline sync (roadmap Plans 2–4) |

**This is not what `TODO.md`'s "Proposed settlement" paragraph currently says**
(that paragraph has BusKá keeping Foreground IP with a license grant to
PaqTcPB). That paragraph is a developer's placeholder, not a signed position.
§2 of this document reflects the intended position going forward; `TODO.md`
should be updated to match once confirmed, and the actual contract amendment
is the only thing that settles it for real.

**Architectural consequence:** code that is PaqTcPB's Foreground IP must never
be merged into the Background IP core that BusKá resells to future clients.
The repo/package boundary described in §4 exists specifically to make that
distinction mechanical instead of a judgment call on every PR.

## 3. Current state (as of this writing)

| Repo | Role | Status |
|---|---|---|
| `municipal-backend` | Original product — fixed-route school transport | Active, mature (400+ commits); still owns its fixed-route features inline rather than consuming a shared core — see §6 step 6 |
| `corporate-backend` | Full fork of `municipal-backend` for the PaqTcPB engagement | 1 month old, duplicated code, no fix-forward from `municipal-backend` |
| `buska-core` | Intended shared library | Empty, never populated, nothing depends on it — the repo exists, the job doesn't |
| `PaqTcPB/mebuska-deploy` | PaqTcPB-specific seed data + plugin slot | Real, thin, correctly scoped |
| `municipal-frontend` | Rider + driver + manager app (mobile + web via RN-web) | Active |
| `corporate-frontend` | Intended PaqTcPB-facing app | Empty, never populated |
| `landing-page` | Marketing site | Active, unrelated to this split |

`corporate-backend`'s biggest problem isn't that it's separate from
`municipal-backend` — it's that it mixes duplicated Background IP (copied
controllers/services/models) with new Foreground IP (the DRT-specific work)
in one undifferentiated tree. Nobody can point at "the PaqTcPB-owned part"
without file-by-file archaeology. That ambiguity is itself a risk, independent
of how §2 resolves.

## 4. Target architecture

**Rule: the code boundary matches both the ownership boundary and the
"who actually needs this" boundary.** A minimal shared core, with every
segment's feature set — municipal's fixed routes included — as an equally
optional module on top of it. Municipal's feature set is not the default
that other clients get measured against and trimmed down from; it's one
module among several, same tier as PaqTcPB's.

This is a direct answer to something municipal-backend's own scale doesn't
solve on its own: PaqTcPB won't use every feature municipal-backend has, and
a plausible future client won't use every feature either product has. Trimming
a copy (what `corporate-backend`'s TODO Task 4 did — delete two municipal-only
modules from a full fork) only removes what one specific client didn't need;
it doesn't stop the next fork from re-duplicating the ~90% every client *does*
need. A real minimal core does.

```
buska-core (BusKá, Background IP — the only mandatory piece)
  ├─ auth, RBAC, tenancy (Organizacao/tenant model), user roles
  ├─ geo primitives, vehicle registry, notifications, error handling
  └─ plugin-discovery mechanism (mebuska.plugins entry points)
        ▲                                        ▲
        │ depends on                             │ depends on
        │                                        │
municipal fixed-route module           mebuska-deploy (PaqTcPB, Foreground IP)
  (route subscription, scheduled         ├─ paqtcpb/dados.py, seed.py (existing)
   routes, batch trip generation —       └─ paqtcpb/plugins/drt_engine.py — trip
   currently inline in                      lifecycle, capacity engine, buffer
   municipal-backend; extracting            window, QR boarding (Plans 2–4)
   it is §6 step 6, not urgent)
```

A third client with a different feature mix depends on the same `buska-core`
and brings only the module it needs — not a trimmed copy of either existing
app.

**This is a repo/codebase diagram, not a runtime diagram, and the two are not
symmetric.** Governments already share one running instance:
`municipal-backend` is one deployed service, one database, serving many
prefeituras through tenant isolation — that's what the `Organizacao` model is
for, and nothing here changes it. Companies do **not** default to that same
shared-runtime model: each corporate client gets its own deployment (its own
database, its own release cadence) — `mebuska-deploy` for PaqTcPB, a sibling
repo with the same shape for the next one. Two reasons, not one:

1. **IP.** A company's DRT module is typically their Foreground IP (§2). A
   shared multi-tenant service running PaqTcPB's owned code to also serve a
   second company would be using PaqTcPB's IP without a license — the exact
   commingling this document exists to prevent.
2. **Confidentiality expectations.** Municipalities don't generally object to
   sharing infrastructure with other municipalities on a government SaaS
   platform. Private companies — plausibly competitors of each other — expect
   stronger isolation than that.

If BusKá later builds or licenses a genuinely generic DRT capability (not
PaqTcPB-specific), a shared multi-tenant corporate product symmetric to
`municipal-backend` becomes possible. That's gated on the IP situation
allowing it and on more than one company actually wanting the same DRT
flavor — not something to design for yet, just worth naming so the current
per-client deployment shape isn't mistaken for a permanent limitation.

Frontend mirrors the same rule, with one adjustment: a compiled mobile app has
no runtime plugin loading, so the "plugin" is a JS package pulled in at build
time via a flavor, not discovered at startup.

```
municipal-frontend (BusKá, Background IP)
  ├─ rider, driver, manager screens — tenant-aware
  └─ react-native-config-driven build flavors
        ▲
        │ imports as a package, only for the PaqTcPB build flavor
        │
corporate-frontend (PaqTcPB, Foreground IP)
  ├─ brand assets (icon, splash, colors)
  └─ DRT screens (ride request, buffer countdown, QR boarding)
```

Net effect versus today: `corporate-backend` is retired (its Background IP
content is absorbed into `buska-core`, its Foreground IP content moves into
`mebuska-deploy`). `buska-core` goes from empty to being the actual shared
core — it survives, it just finally does the job its name always implied.
`corporate-frontend` is repurposed rather than left empty. **Seven repos
become six**, not five as an earlier pass at this document said — that
earlier version had `buska-core` being retired alongside `corporate-backend`,
which was wrong once the core is meant to outlive both product-specific apps.
No new repos are created either way.

## 5. What does NOT belong in `buska-core`

Nothing segment-specific belongs in the shared core — not PaqTcPB's DRT work,
and not municipal's fixed-route scheduling either, even though the latter was
there first. "It's already in `municipal-backend`" is not a reason to promote
something into `buska-core`; "every current and plausible future client needs
this regardless of their trip model" is the only test that counts.

If a capability is specific to one contract — anything under RF-05, RF-10
through RF-19 in the PaqTcPB requirements doc, or anything specific to
scheduled school routes (route subscription, batch trip generation) — it does
not go in the core, even if it looks reusable. `docs/plugins.md` already
states the inverse rule for routes ("if it's not client-specific, it's not a
plugin"); this is the mirror of that at the core/module boundary. Reusing
PaqTcPB's Foreground IP for a future client is a licensing conversation with
PaqTcPB, not a refactor.

## 6. Migration plan

1. **Settle §2 in writing.** Everything below is easier, and some of it
   becomes safe to do, only once ownership isn't ambiguous.
2. **Build `buska-core` for real.** Extract the universal primitives —
   auth, RBAC, tenancy, geo primitives, notifications, error handling, the
   plugin-discovery mechanism — as a package. Source only from
   `municipal-backend`, never from `corporate-backend` (see §2: anything
   touched inside `corporate-backend` since the fork was modified under the
   PaqTcPB-funded engagement and is presumptively Foreground IP until
   confirmed otherwise).
3. **Move DRT work into `mebuska-deploy`, built against `buska-core`.**
   Plans 2–4 (trip lifecycle, capacity engine, boarding) get built as
   `paqtcpb/plugins/drt_engine.py` (or a small set of modules under
   `paqtcpb/plugins/`), depending on `buska-core` directly — not inside
   `corporate-backend`, and not depending on `municipal-backend`.
4. **Retire `corporate-backend`.** Delete or archive once steps 2–3 leave
   nothing behind worth keeping.
5. **Repurpose `corporate-frontend`.** Brand assets + DRT feature module,
   consumed by `municipal-frontend`'s PaqTcPB build flavor.
6. **Retrofit `municipal-backend` onto `buska-core` — lower urgency, do
   carefully.** `municipal-backend` is a live production system serving real
   prefeituras. Carving its fixed-route features (route subscription,
   scheduled routes, batch trip generation) out into their own module and
   making the app consume `buska-core` internally, instead of owning its own
   copy of auth/geo/notifications, is the architecturally consistent end
   state — but it's a strangler-fig job on running code, not a blocker for
   fixing the PaqTcPB-facing duplication. Sequence it module by module,
   behind the existing test suite, after steps 2–5 are stable. Until this
   step happens, `buska-core` and `municipal-backend` each maintain their own
   copy of the shared primitives — the duplication problem this document
   exists to solve isn't fully closed until step 6 lands, only contained to
   one side of it.

Steps 2–5 are independent of each other in sequencing except where noted;
step 1 gates nothing about *starting* `buska-core` extraction (that's
Background IP, safe today), but does gate moving or building anything that
is unambiguously Foreground IP. Step 6 is deliberately last, open-ended, and
the one place this plan still leaves duplication in place on purpose.

## 7. Open questions

- **Naming.** Is "MeBusKá" the company rebrand or product 2's name? Blocks
  final repo naming. (Carried over from `TODO.md`, still open.)
- **Telemetry device auth.** The van's telemetry reader needs a long-lived
  token with no rotation or revocation path today, per `mebuska-deploy`'s own
  README. Needs a device-identity concept before production.
- **Alembic downgrade-to-base.** Known broken migration artifact inherited
  from `municipal-backend`; low priority, documented in `docs/migrations.md`.
