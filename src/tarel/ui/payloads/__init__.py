"""JSON payloads the browser renders.

``graph`` builds the Space payload for one graph or a workspace; ``families``, ``logical`` and
``focus`` add optional layers to it; ``lineage`` builds the Lineage canvas. Payload builders are
pure functions of stored documents: they never write state or call connectors and providers.
"""
