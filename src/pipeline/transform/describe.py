"""T2: describe and categorise, one structured call per risk (SPECS.md > TRANSFORM).

The prompt carries the taxonomy and the mapping rule. The ESRS topic code narrows the prior.
When category confidence is low, extra samples are drawn and the majority category wins.
Every call is recorded for replay. Poor-fit flags are counted on the run record.
"""

from __future__ import annotations

from collections import Counter

from shared.config import ESRS_CATEGORY_PRIOR, LOW_CONFIDENCE, SELF_CONSISTENCY_SAMPLES
from shared.runrecord import RunRecord
from shared.schema import CandidateRisk, DescribeOutput, DescribedRisk, IdentifyResult
from shared.llm import LLMClient, load_prompt


def _user_message(c: CandidateRisk) -> str:
    parts = [f"Register: {c.source_register.value if c.source_register else 'n/a'} (prominence {c.prominence}; 1 = enterprise main risk, 2 = ESRS financially material risk)",
             f"Section: {c.section}, printed page {c.page}", f"Title as printed: {c.verbatim_title}"]
    if c.source_taxonomy:
        prior = ", ".join(ESRS_CATEGORY_PRIOR.get(c.source_taxonomy, ()))
        parts.append(f"ESRS topic: {c.source_taxonomy}" + (f"; sub-topic: {c.sub_topic}" if c.sub_topic else "") + (f"; likely categories: {prior}" if prior else ""))
    if c.value_chain:
        parts.append(f"Value chain: {c.value_chain}")
    parts.append(f"\nDescription as printed:\n{c.verbatim_span}")
    if c.potential_impact:
        parts.append(f"\nPotential impact as printed:\n{c.potential_impact}")
    parts.append(f"\nHow we manage it, as printed:\n{c.stated_mitigation}" if c.stated_mitigation else "\nThe text states no mitigation for this row.")
    return "\n".join(parts)


def describe_one(c: CandidateRisk, client: LLMClient, system: str) -> DescribedRisk:
    out, call_id = client.complete(f"describe-{c.candidate_id}", system, _user_message(c), DescribeOutput)
    calls, votes = [call_id], Counter([out.category.value])
    if out.confidence < LOW_CONFIDENCE:
        for s in range(1, SELF_CONSISTENCY_SAMPLES):
            alt, cid = client.complete(f"describe-{c.candidate_id}", system, _user_message(c), DescribeOutput, sample=s, temperature=0.7)
            calls.append(cid)
            votes[alt.category.value] += 1
        winner, n = votes.most_common(1)[0]
        if winner != out.category.value:
            out = out.model_copy(update={"category": winner, "confidence": n / SELF_CONSISTENCY_SAMPLES})
    return DescribedRisk(candidate_id=c.candidate_id, output=out, call_ids=calls, votes=dict(votes))


def describe(identified: IdentifyResult, record: RunRecord, client: LLMClient) -> list[DescribedRisk]:
    system = load_prompt("describe", client.prompt_version)
    out = [describe_one(c, client, system) for c in identified.candidates]
    poor = [d.candidate_id for d in out if d.output.poor_fit]
    voted = [d.candidate_id for d in out if len(d.call_ids) > 1]
    record.add("transform", "category_poor_fit", "ok", count=len(poor), candidates=poor, self_consistency_runs=voted,
               model=client.model, prompt_version=client.prompt_version)
    return out
