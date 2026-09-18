"""Authentication domain module: password policy, JWT, service, dependencies, routes.

Layout mirrors the rest of the app — routes stay thin, the service owns the
transaction, repositories own the queries, and crypto primitives live in
``app.core.security`` (single implementation, no duplication).

NOTE: this package init stays import-free on purpose: ``app.core.security``
delegates to ``app.auth.tokens``, so importing the service layer here would
create a cycle. Import from ``app.auth.service`` / ``app.auth.dependencies``
directly.
"""
