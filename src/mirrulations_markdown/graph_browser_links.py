"""Build links from graph records to the existing local comment browser."""

from urllib.parse import quote


def comment_browser_url(
    *, browser_base_url, comment_id, representation_id=None, stage_number=None,
    block_id=None,
):
    if stage_number is not None and representation_id is None:
        raise ValueError(
            "graph_browser_links.py Error: stage_number requires representation_id"
        )
    if block_id is not None and stage_number is None:
        raise ValueError(
            "graph_browser_links.py Error: block_id requires stage_number"
        )
    base_url = browser_base_url.rstrip("/")
    encoded_comment_id = quote(str(comment_id), safe="-")
    url = f"{base_url}/comments/{encoded_comment_id}/"
    if representation_id is not None:
        encoded_representation_id = quote(str(representation_id), safe="-")
        url += f"representations/{encoded_representation_id}/"
    if stage_number is not None:
        if int(stage_number) < 1:
            raise ValueError(
                "graph_browser_links.py Error: stage_number must be positive"
            )
        url += f"stage/{int(stage_number)}/"
    if block_id is not None:
        url += f"#{quote(str(block_id), safe='-')}"
    return url