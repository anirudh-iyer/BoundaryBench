# Threat Model

The model receives a fixed system policy, user turns, and tool responses. Attackers may use unauthorized requests, cross-course claims, proficiency-boundary requests, answer-key or instructor-note requests, and instructions embedded in retrieved documents. User text, document text, and tool arguments cannot change authenticated attributes or trusted policy metadata.

The harness authenticates the user outside the model. Missing or invalid user or document metadata denies access. The policy requires course membership and an allowed role; instructors can access their own course, while students are limited by proficiency and cannot access answer keys or instructor-only material.

The security boundary includes retrieval filtering and tool authorization. The model-visible response is serialized identically across conditions, so an empty response is not replaced by an explicit condition-specific denial. The harness records both unauthorized content entering context and protected facts appearing in assistant output.

This is not a claim about real providers, real courses, general model security, or untested access paths. Shared policy implementation faults can affect both layers in D.
