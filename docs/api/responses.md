# Responses

Response builders for hook handlers.

## Response Functions

::: fasthooks.responses.allow
    options:
      show_root_heading: true

::: fasthooks.responses.deny
    options:
      show_root_heading: true

::: fasthooks.responses.block
    options:
      show_root_heading: true

::: fasthooks.responses.approve_permission
    options:
      show_root_heading: true

::: fasthooks.responses.deny_permission
    options:
      show_root_heading: true

## Response Classes

::: fasthooks.responses.BaseHookResponse
    options:
      members:
        - decision
        - reason
        - should_return
        - to_json

::: fasthooks.responses.HookResponse
    options:
      members:
        - decision
        - reason
        - message
        - interrupt
        - to_json
