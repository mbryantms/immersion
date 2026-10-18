/** DOM selection -> half-open source offsets, measured in Unicode codepoints.
 * Ruby annotations never contribute; rendered script variants use source positions.
 */
export function sourceSelection(range: Range): { sentenceId: number; start: number; end: number } | null {
  const boundary = (container: Node, offset: number) => {
    const element = container instanceof Element ? container : container.parentElement;
    if (element?.closest("rt")) return null;
    const token = element?.closest<HTMLElement>("[data-source-start]");
    const sentence = token?.closest<HTMLElement>("[data-sentence-id]");
    if (!token || !sentence) return null;
    const prefix = document.createRange();
    prefix.selectNodeContents(token);
    prefix.setEnd(container, offset);
    const content = prefix.cloneContents();
    content.querySelectorAll("rt").forEach((rt) => rt.remove());
    return { sentenceId: Number(sentence.dataset.sentenceId), offset: Number(token.dataset.sourceStart) + [...(content.textContent ?? "")].length };
  };
  const start = boundary(range.startContainer, range.startOffset);
  const end = boundary(range.endContainer, range.endOffset);
  if (!start || !end || start.sentenceId !== end.sentenceId || end.offset <= start.offset) return null;
  return { sentenceId: start.sentenceId, start: start.offset, end: end.offset };
}
