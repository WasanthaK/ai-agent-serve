from inbound import NormalizedInboundMessage


def normalize_website_message(
    *,
    authenticated_channel: str,
    text: str,
) -> NormalizedInboundMessage:
    """Translate an authenticated website delivery into the common inbox contract.

    `authenticated_channel` must come from the channel authentication boundary,
    never from an untrusted normalized payload.
    """

    return NormalizedInboundMessage(
        channel=authenticated_channel,
        text=text,
    )
