"""Context packets: the bounded, hashed slice of a graph that a harness hands to a model.

``compiler`` selects objects, joins and paths within explicit budgets; ``output`` defines the
packet contract and its canonical JSON; ``packets``, ``guidance`` and ``caching`` compare, brief
and split stored packets; ``hints`` adds optional logical-layer hints; ``grounding`` combines a
packet with source routing and lineage for harness prompts. ``application`` and the
``*_application`` modules are the use cases the CLI and SDK call.
"""
