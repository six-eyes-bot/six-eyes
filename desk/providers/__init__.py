"""Provider adapters. Each one speaks to exactly one upstream.

Providers are dumb: they fetch, they normalise shape, and they raise. They do
NOT decide about fallback, caching or liveness — MarketDataService owns all
three, because those decisions depend on the whole matrix and no single
provider can see it.
"""
