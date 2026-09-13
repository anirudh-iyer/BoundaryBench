# Development fixtures only

`cases.jsonl` contains 14 hand-authored development cases covering ordinary
learning, answer keys, proficiency, course membership, instructor-only content,
role impersonation, paraphrase, multi-turn escalation, inference, and retrieved
injection. It includes authorized counterparts and a clean injection counterpart.
These cases are reusable for debugging and must never be relabelled held-out.
There are no held-out evaluation cases.

All arbitrary markers were authored as synthetic fixture values, not extracted
from real assessments. Their topics (for example, Unit 4 oral examination) occur
in requests; their secret values do not occur in any scripted turn or injection.
The same-course instructor and sufficiently proficient students have authorized
counterparts. A value's protected status depends on the authenticated user.

`evaluator_only_*` fields are labels/rubrics, not model inputs. The loader audits
secret absence in prompts and accessible material for each security case.
In-gate means an ordinary authorized request. The injection case is labelled
out-of-gate for its attacker objective and separately has `authorized_task=true`
for legitimate utility. Its user request exactly matches the clean counterpart;
only the authorized carrier document's body changes. Every score preserves both
gate and authorized-task applicability. The tiny corpus is a control-logic
fixture, not the planned full synthetic environment or a representative sample.
