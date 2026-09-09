# How the creative studio is evaluated

Read this page if you decide what this service is allowed to publish. The metrics, the bars, the
corpora and the copy floor below are generated from the artifacts that actually gate the build,
so they cannot drift from what runs: `make evals-doc-check` fails the build when this page and
those artifacts disagree.

## How to run it

```sh
make eval              # the deterministic half, offline, no credentials
make eval-narrative    # the judged half, offline by default, no model server
make evals-doc-check   # this page is still true
```

`make gate` runs all three on every change.

## The probe was one-sided, and that was the gap

`brand_safety_detection` feeds the studio a deliberately bad variant and checks it is flagged.
That proves the detector fires. It says nothing about whether the copy the studio actually writes
is any good, and the golden set carried no expected outputs at all. In a service whose product IS
the copy, that was the measurement most obviously missing.

**Bad copy that is brand-safe is what gets published.** A variant can pass every rule in the pack
and still make an unsubstantiated superlative claim, promise something the product does not do, or
end on a call to action that names no action. None of those is unsafe; all three are wrong, and
only a judgement catches them. That is what the judged half grades, against a model-risk floor.

## The image port had no coverage at all

`ImageGenerationPort` is the only image port in the fleet and nothing scored it. Nothing checked
that the asset came back at the dimensions asked for, with alt text, or with provenance. All four
matter for a marketing asset and the last two reach a person directly: an image with no alt text
fails accessibility outright, and one with no citation is an asset nobody can say who made.

`image_spec_compliance` scores all four at 1.0, through the adapter the CONTAINER binds rather
than a stub written in the eval, so the managed Imagen path is measured by the same rule. The bar
is 1.0 because at 0.75 a single missing field would pass, and the single missing field that
matters most is exactly the one a busy adapter drops.

## What is measured, and against what bar

Every bar below lives in `eval/rubrics/*.yaml` next to the argument for it, and the
runner reads it from there. There is no dict of thresholds in the runner any more: a
metric scored with no reviewed bar fails the build, and so does a bar that names no
metric, which is the direction that rots quietly because it rots toward looking well
governed.

The third column is the denominator rule, and it applies only where a score is a
FRACTION over scored positives: such a threshold `t` tolerates a single miss only over
at least `1/(1-t)` of them. `all or nothing` marks a bar that already asks for no
headroom, so a bigger corpus would not change what it means. Each rubric declares which
it is rather than the rule being guessed from the number.

| Metric | Bar | Denominator | What it measures |
|---|---|---|---|
| `brand_safety_detection` | 0.8 | a rate; needs 5 positives | Fraction of golden cases where the studio FAILS a deliberately non-compliant probe variant (so unsafe creative is reliably caught). |
| `check_groundedness` | 0.8 | a rate; needs 5 positives | Fraction of findings that carry at least one citation to the rule / policy / spec they enforce. A finding raised without a citation fails. |
| `citation_accuracy` | 0.9 | a rate; needs 10 positives | Fraction of cited sources whose type is one of the four rule namespaces (brand, claim, policy, asset). No fabricated citations. |
| `image_spec_compliance` | 1 | all or nothing | The generated image satisfies the request it was made for: the width and height asked for, non-empty alt text, and a provenance citation naming the model that produced it. |
| `review_safety` | 1 | all or nothing | Every creative result requires human review before anything is published, and the escalation is routed rather than left as a flag. |

Scored over 6 golden creative briefs.

## What is exercised

- **6 golden creative briefs** in `eval/datasets/golden_creative.jsonl`,
  covering both verticals. The studio drafts variants for each, and one image asset per
  brief is scored through whatever adapter the container binds.
- **One deliberately bad variant**, used as the brand-safety probe. It is one-sided by
  construction: it proves the detector fires, and says nothing about whether the copy the
  studio writes is any good.
- **2 judged copy cases** in `eval/datasets/narrative_golden.jsonl`, each
  written once per profile with the band it is expected to land in. This is the half the
  probe cannot see, and a profile that quietly got BETTER fails too.

## Where the narrative floor comes from

`config/quality-floors.toml` is owned by model risk. A **floor** refuses: below it a
profile must not serve this vertical, which is not the same as serving it worse. A
**target** is full quality. Between the two is DEGRADED, the band a portability claim
describes in adjectives and which nothing measured until there was a floor.

| Vertical | Floor | Target | Why |
|---|---|---|---|
| `mkt3-creative` | 0.65 | 0.88 | Copy a marketing reviewer reads before it is published. The brand-safety detector catches what is forbidden; nothing else catches copy that is merely bad, and bad copy that is brand-safe is what gets published. |

## What is NOT measured here

- **A real model's words.** The deterministic metrics score a deterministic core, and the judged
  half grades written-down copy rather than copy a model produced in this run.
- **Whether an image looks right.** `image_spec_compliance` scores the asset's contract, not its
  content. Nothing here can tell a good illustration from a bad one.
- **Production traffic.** Everything here is a golden set. Nothing samples live requests.
