# Installation-owned first-key custody

This increment implements the automatic key custody selected in
`NATIVE_SURFACE_PUSH_V1.md`. It does not enroll an installation, construct a
WidgetIssuerOwner or enable a native role. The existing first-key protocol and
actual API/native acknowledgements remain mandatory.

`NativePairEnrollment(hass, transport, publisher=publisher)` may now create its
own dormant `InstallationWidgetKeyCustodian` when no explicit selection is
provided. Constructing it performs no file, key, SDK or network operation.
The production composition still has to supply genuinely selected transport and
publisher custody; this change does not choose CF credentials, mount an operator
file as the default or replace the existing HA-dev configuration path.

Key capture requires the actual loaded original pair and persisted PairJournal,
the existing stored installation credential, explicit current SQLite WidgetKit
consent, and the existing persisted device/Profile/source observation. The
original source, consent revision, credential, selected service, transport and
publisher are rechecked across awaited operations. Other channels are closed.
The existing WidgetEnrollmentSelection produces the exact original HMAC binding
dialect and P-256 signer; no Surface binding namespace is copied or equated.

Custody uses an HA private atomic Store (`private=True, atomic_writes=True`).
Its name is derived from the actual origin, installation and original committed
PairJournal registration binding; the private record
is bound to the original pair-store/generation and credential identity/digest.
A different credential cannot silently turn the same original pair into a fresh
key. Each genuinely fresh ordinary pair requires its own explicit opt-in and
receives a separate partition; no installation-global signing key is claimed. The original credential remains secret in its existing store.
No private signing/binding material, token or stored record enters the wire,
logs or qualification evidence.

An exclusive mode-0600 original claim is fsynced, including its directory, before
any key generation is scheduled. Only the winner may generate once. A missing
key with an existing claim is UNKNOWN, including after cancellation, a lost
write acknowledgement or process restart: it may not generate again. A valid
private atomic key record with its exact original claim can reload the same key;
that is custody recovery, not a registered-key receipt or an issuer grant.
Malformed, mismatched, symlinked, publicly readable or orphaned state fails
closed and is never overwritten, reset or automatically migrated. Normal
explicit recovery is required. The API can independently reject first trust;
local key creation does not assert that its key registry is empty or enrolled.

The unit qualification uses real P-256 signatures, the actual SQLite pair and
consent implementations, committed profile/source storage and private local
atomic files. The test file store models HA Store writes; it is not a production
HA SDK run. Existing SDK source confirms atomic private Store writes use the
filesystem atomic writer, but that inspection does not prove an installed HA
runtime, API admission, APNs, WidgetKit/ActivityKit or physical device acceptance.
The separate winning-registration handoff still requires the genuine received
API ACK and original lifetime. Actual widget delegation, channel target, field
policy, issuer lifecycle and SDK/native enrollment remain separate gates.
