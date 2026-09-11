"""Mock TicketHub services under test.

These stand in for the real ``orders`` and ``payments`` microservices in
``kubernetes_full_microservices/repo/services``. They implement just enough
domain behaviour -- and a *transient fault* switch -- to drive the pytest suite
and produce realistic structured step-logs for the triage engine to chew on.

The transient-fault model is deliberate: a step fails on its **first** attempt and
succeeds on the **second**, which is exactly the shape that ``resume-on-retry``
tracking is built to tell the story of.
"""
