/** Indexes of primary-stress tokens from a 1–3 stress_pattern array. */
export function peakStressIndexes(
  pattern: number[] | null | undefined,
): Set<number> {
  if (!pattern?.length) return new Set()
  const peak = Math.max(...pattern)
  const indexes = new Set<number>()
  pattern.forEach((mark, index) => {
    if (mark === peak) indexes.add(index)
  })
  return indexes
}

/** True when karaoke timestamps align with stress_pattern length. */
export function stressPatternAligns(
  pattern: number[] | null | undefined,
  tokenCount: number,
): boolean {
  return Boolean(pattern && pattern.length > 0 && pattern.length === tokenCount)
}
