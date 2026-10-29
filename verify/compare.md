# Re-check of G01-G10: compare (A)

Verdicts: B's table and mine agree on all 53 bugs: 51 fixed (HM-05 by its
test in both, FC-10 and FC-12 by test in B's; I saw them live on a hub copy
where Alaska reads 0), DA-02 and RE-17 for Ely as recorded.

Findings:
- 1, the Retro form's "runners" (`width: int = Form(4)`): accepted by B,
  who re-checked it (422 on 2e0). Agreed: one group, V01 `retro-runners`,
  from G02, so B decides.
- 2: withdrawn by me, agreed by B.
- B's two notes (the pill's localStorage `fcmode`; a refused non-number
  kept in the form's number box): older than the run and outside the 53.
  I agree they are not findings. The second is G02's decision (the panel
  keeps the typed value beside its reason).

My V01 proposal is pushed (V01/proposal.md, V01/proposal.patch).
