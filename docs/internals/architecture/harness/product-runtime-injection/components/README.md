# Product Runtime Injection Component Designs

## Status

Directory reserved for detailed, capability-specific binding contracts.
No component implementation is implied by the presence of this directory.

## Authoring Rule

Add one document here immediately before the migration wave that makes the
corresponding capability dynamically selectable. Do not combine unrelated
capabilities merely because they currently live in the same Coding controller.

Every component document follows the template in
[the component inventory](../01-component-inventory.md#common-detailed-design-template)
and links back to the requirements it satisfies.

## Planned Documents

```text
runtime-profile-resolution.md
runtime-binding-lifecycle.md
session-runtime-core.md
conversation-store-binding.md
transcript-profile-binding.md
memory-binding.md
context-compaction-binding.md
artifact-store-binding.md
prompt-binding.md
skill-binding.md
method-binding.md
resource-binding.md
tool-pack-binding.md
command-pack-binding.md
model-auth-binding.md
policy-approval-binding.md
presentation-theme-binding.md
extension-oem-contribution-binding.md
```

The initial implementation order is defined by the migration-coupling table in
the component inventory, not by this filename order.
